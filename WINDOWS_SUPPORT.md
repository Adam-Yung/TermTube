# TermTube — Windows Support Plan

## Overview

Full Windows compatibility for TermTube, targeting Windows 10 21H2+ and Windows 11. Windows Terminal natively supports Sixel graphics (since v1.22) and modern VT sequences, making it viable for TermTube's rich TUI without degradation.

---

## 1. Installation & Dependencies

### Package Management — winget

| Tool | winget ID | Notes |
|------|-----------|-------|
| Python 3.12+ | `Python.Python.3.12` | py launcher standard on Windows |
| yt-dlp | `yt-dlp.yt-dlp` | Ships as .exe, no pip needed |
| mpv | `mpv.net` | mpv.net wraps mpv with Windows integration |
| ffmpeg | `Gyan.FFmpeg` | Static build, added to PATH |
| chafa | `hpjansson.Chafa` | Terminal thumbnail fallback (same as Unix) |

### Installer: `setup.ps1`

Already drafted (see `setup.ps1`). Key differences from Unix:
- Uses `%LOCALAPPDATA%\TermTube` instead of `~/.local/share/TermTube`
- Uses `%APPDATA%\TermTube` for config (instead of `~/.config/TermTube`)
- Creates a `termtube.cmd` launcher batch file
- Uses NTFS junctions for `--sync` mode (symlinks require admin)
- Adds to user PATH via registry (`[Environment]::SetEnvironmentVariable`)

### Uninstaller: `uninstall.ps1`

Already drafted (see `uninstall.ps1`). Features:
- Cleans PATH registry entries
- Kills running processes before removal
- `--Purge` flag for complete removal
- Handles junctions safely

---

## 2. Path Handling

### Current Problem

Hardcoded Unix paths throughout the codebase:
- `Path.home() / ".config" / "TermTube"` — wrong on Windows
- `/tmp/termtube-mpv.sock` — Unix socket path
- `~/.local/share/TermTube` — not a Windows convention

### Solution: Platform-aware path resolution

```python
import platform
from pathlib import Path

def get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "TermTube"

def get_data_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "TermTube"

def get_cache_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "TermTube" / "cache"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "TermTube"
```

### Files to modify:
- `src/config.py` — `_CONFIG_DIR`, `DEFAULT_CONFIG` paths
- `src/cache.py` — cache directory resolution
- `src/logger.py` — log directory (`$TMPDIR` → `%TEMP%`)
- `src/main.py` — any hardcoded paths

---

## 3. IPC / Socket Communication (mpv)

### Current Problem

mpv IPC uses Unix domain sockets (`/tmp/termtube-mpv.sock`). Windows doesn't support `AF_UNIX` reliably (only recent Windows 10 builds, and not via named paths in the Unix sense).

### Solution: Named Pipes on Windows

```python
import platform

def get_ipc_path() -> str:
    if platform.system() == "Windows":
        return r"\\.\pipe\termtube-mpv"
    return "/tmp/termtube-mpv.sock"
```

mpv on Windows supports `--input-ipc-server=\\.\pipe\NAME` natively.

### IPC client changes (`src/player.py`)

On Windows, connect to named pipes instead of Unix sockets:

```python
import platform

def _connect_ipc(socket_path: str, timeout: float = 1.0):
    if platform.system() == "Windows":
        # Named pipe connection
        import win32file, win32pipe  # pywin32
        handle = win32file.CreateFile(
            socket_path,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None,
            win32file.OPEN_EXISTING,
            0, None
        )
        return PipeConnection(handle)
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        return SocketConnection(s)
```

**Alternative (simpler, no pywin32 dependency):** Use mpv's `--input-ipc-server` with a TCP socket on localhost:

```python
def get_ipc_address():
    if platform.system() == "Windows":
        return ("127.0.0.1", 9632)  # TCP fallback
    return "/tmp/termtube-mpv.sock"  # Unix socket
```

This avoids `pywin32` but requires mpv to be started with `--input-ipc-server=tcp://127.0.0.1:9632` on Windows. **Recommendation: use named pipes** (the standard mpv approach on Windows).

### Dependency consideration

- Option A: Add `pywin32` as a Windows-only dependency in `requirements.txt`
- Option B: Use Python 3.12+ `AF_UNIX` support on Windows (limited, but works for recent builds)
- Option C: Use raw `ctypes` calls to Windows pipe APIs (no extra dependency, more code)

**Recommendation:** Option A (`pywin32`) — well-maintained, comprehensive, standard for Windows Python.

---

## 4. Process Management

### Current Problem

- `subprocess.run` / `Popen` work cross-platform, but signal handling differs
- `pkill -f "termtube"` in uninstaller — no equivalent on Windows
- `os.unlink()` on sockets — not applicable to named pipes
- `pgrep` — not available on Windows

### Solution

```python
import platform, subprocess

def kill_process_tree(pid: int):
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                      capture_output=True)
    else:
        import signal
        os.killpg(os.getpgid(pid), signal.SIGTERM)

def cleanup_ipc():
    ipc = get_ipc_path()
    if platform.system() != "Windows":
        # Unix: remove socket file
        try:
            os.unlink(ipc)
        except OSError:
            pass
    # Windows: named pipes are kernel objects, auto-cleaned on process exit
```

### mpv process handling

- Use `subprocess.CREATE_NO_WINDOW` flag on Windows for headless audio
- Use `subprocess.CREATE_NEW_PROCESS_GROUP` for proper Ctrl+C isolation

```python
def _spawn_mpv(cmd: list[str], *, headless: bool = False):
    kwargs = {}
    if platform.system() == "Windows":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if headless:
            creation_flags |= subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = creation_flags
    return subprocess.Popen(cmd, **kwargs)
```

---

## 5. Terminal & Graphics

### Windows Terminal Sixel Support

Windows Terminal v1.22+ supports Sixel natively. Detection:

```python
def supports_sixel() -> bool:
    if platform.system() == "Windows":
        # Check if running in Windows Terminal
        return "WT_SESSION" in os.environ
    # Unix: query terminal via DA1 escape sequence
    ...
```

### chafa on Windows

chafa is available via winget (`winget install hpjansson.Chafa`) and works identically to Unix. The thumbnail fallback chain is the same on all platforms:

1. textual-image (Kitty/Sixel) when the terminal supports image protocols
2. chafa symbol art when textual-image isn't available
3. No thumbnails only if neither is installed

### Clipboard

Current: `pbcopy` (macOS) / `xclip` / `wl-copy` (Linux)

```python
def copy_to_clipboard(text: str):
    if platform.system() == "Windows":
        subprocess.run(["clip.exe"], input=text.encode(), check=True)
    elif platform.system() == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    else:
        # Try wl-copy, then xclip, then xsel
        ...
```

---

## 6. Implementation Phases

### Phase 1: Foundation (no breaking changes)

1. Create `src/platform.py` module with all platform detection utilities
2. Refactor path resolution in `config.py` to use platform-aware helpers
3. Refactor `cache.py` and `logger.py` path handling
4. Add `platform.system()` guards to `player.py` IPC code (keep Unix working)
5. Add `setup.ps1` and `uninstall.ps1` (done)

### Phase 2: IPC & Process Management

1. Implement named pipe IPC client for Windows
2. Add `pywin32` as Windows-only dependency (or use ctypes)
3. Refactor `player.py` to use platform-appropriate IPC
4. Handle `CREATE_NO_WINDOW` for background mpv
5. Test audio playback, seek, pause on Windows

### Phase 3: Terminal & UX

1. Detect Windows Terminal for Sixel support
2. Handle chafa absence gracefully (textual-image fallback only)
3. Implement `clip.exe` clipboard support
4. Test in Windows Terminal, PowerShell 7, and legacy cmd.exe
5. Handle `termtube.cmd` launcher edge cases

### Phase 4: Testing & Polish

1. CI matrix: test on Windows (GitHub Actions `windows-latest`)
2. Document Windows-specific setup in README
3. Test winget install flow end-to-end
4. Handle Windows Defender / SmartScreen warnings for first-run scripts
5. Test with both Python from Microsoft Store and python.org installer

---

## 7. Files Requiring Changes

| File | Change |
|------|--------|
| `src/config.py` | Platform-aware config/data paths |
| `src/cache.py` | Platform-aware cache directory |
| `src/logger.py` | Platform-aware temp/log directory |
| `src/player.py` | Named pipe IPC, process flags, pipe cleanup |
| `src/main.py` | Entry point adjustments (if any) |
| `src/tui/app.py` | Clipboard command selection |
| `requirements.txt` | Add `pywin32; sys_platform == "win32"` |
| `termtube` (bash) | N/A on Windows (replaced by .cmd) |
| `setup.ps1` | **New** (done) |
| `uninstall.ps1` | **New** (done) |
| `README.md` | Windows install instructions |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| mpv.net behaves differently than mpv | Test IPC compatibility; fall back to raw mpv if needed |
| pywin32 install fails in venv | Use ctypes as fallback; or ship pure-Python pipe impl |
| chafa unavailable | Rely solely on textual-image; degrade to no thumbnails |
| Windows Store Python has sandboxing | Document preference for python.org installer |
| Path length limit (260 chars) | Use `\\?\` prefix for long paths; keep install paths short |
| Antivirus blocks scripts | Sign scripts or provide manual instructions |

---

## 9. Testing Matrix

| Environment | Terminal | Expected Support |
|-------------|----------|-----------------|
| Windows 11 + Windows Terminal | Full Sixel, full TUI | Full feature parity |
| Windows 10 + Windows Terminal | Sixel (if v1.22+) | Full features |
| Windows 11 + PowerShell 7 | VT sequences, no Sixel | TUI works, no thumbnails |
| Windows 10 + cmd.exe | Basic VT | TUI works, degraded graphics |
| WSL2 | Unix behavior | Already works (Unix path) |
