"""Platform abstraction layer for TermTube.

Centralises all OS-specific logic: paths, IPC, process management, clipboard,
and capability detection. Every other module should import from here rather than
doing ad-hoc platform checks.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

# ── OS Detection ──────────────────────────────────────────────────────────────

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# ── Directory Paths ───────────────────────────────────────────────────────────
# Follow platform conventions:
#   macOS/Linux: XDG Base Directory Specification
#   Windows:     %APPDATA% (roaming config), %LOCALAPPDATA% (local data/cache)


def get_config_dir() -> Path:
    """User configuration directory (~/.config/TermTube or %APPDATA%/TermTube)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "TermTube"


def get_cache_dir() -> Path:
    """Cache directory (~/.cache/termtube or %LOCALAPPDATA%/TermTube/cache)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "TermTube" / "cache"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "termtube"


def get_log_dir() -> Path:
    """Log/temp directory ($TMPDIR/TermTube or %TEMP%/TermTube)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("TEMP", os.environ.get("TMP", Path.home() / "AppData" / "Local" / "Temp")))
    else:
        base = Path(os.environ.get("TMPDIR", "/tmp"))
    return base / "TermTube"


# ── IPC Paths ─────────────────────────────────────────────────────────────────


def get_ipc_path() -> str:
    """Return the mpv IPC socket/pipe path for this platform.

    Unix: /tmp/termtube-mpv.sock (AF_UNIX socket)
    Windows: \\\\.\\pipe\\termtube-mpv (named pipe)
    """
    if IS_WINDOWS:
        return r"\\.\pipe\termtube-mpv"
    return "/tmp/termtube-mpv.sock"


def get_audio_ipc_path() -> str:
    """IPC path for the background audio mpv instance."""
    if IS_WINDOWS:
        return r"\\.\pipe\termtube-mpv-audio"
    return "/tmp/termtube-mpv-audio.sock"


def get_video_ipc_path() -> str:
    """IPC path for the video playback mpv instance."""
    if IS_WINDOWS:
        return r"\\.\pipe\termtube-mpv-video"
    return "/tmp/termtube-mpv-video.sock"


# ── Clipboard ─────────────────────────────────────────────────────────────────


def clipboard_copy(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success."""
    import subprocess
    import shutil

    if IS_WINDOWS:
        try:
            subprocess.run(
                ["clip.exe"],
                input=text.encode("utf-16le"),
                check=True,
                capture_output=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    if IS_MACOS:
        try:
            subprocess.run(
                ["pbcopy"],
                input=text.encode(),
                check=True,
                capture_output=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    # Linux: try wl-copy (Wayland), xclip, xsel
    for cmd in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True, capture_output=True)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
    return False


# ── Process Management ────────────────────────────────────────────────────────


def get_subprocess_flags(*, headless: bool = False) -> dict:
    """Return platform-specific kwargs for subprocess.Popen / subprocess.run.

    Args:
        headless: If True, hide the process window (Windows only).
    """
    import subprocess

    if not IS_WINDOWS:
        return {}

    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if headless:
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags}


def get_popen_kwargs(*, headless: bool = False) -> dict:
    """Return kwargs for subprocess.Popen on any platform.

    On Windows, adds creation flags. On Unix, returns empty dict.
    Use for Popen calls that need platform awareness.
    """
    return get_subprocess_flags(headless=headless)


def terminate_process(proc, *, timeout: float = 3.0) -> None:
    """Gracefully terminate a subprocess, then force-kill if it doesn't exit.

    Works cross-platform: uses terminate() first (SIGTERM on Unix,
    TerminateProcess on Windows), waits briefly, then kills if needed.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass


def cleanup_ipc(ipc_path: str) -> None:
    """Remove the IPC endpoint if applicable.

    Unix sockets leave a file on disk that must be removed.
    Windows named pipes are kernel objects, cleaned up automatically.
    """
    if IS_WINDOWS:
        return
    try:
        os.unlink(ipc_path)
    except OSError:
        pass


# ── Terminal / Graphics Capabilities ──────────────────────────────────────────


def in_windows_terminal() -> bool:
    """True if running inside Windows Terminal (which supports Sixel natively)."""
    return IS_WINDOWS and bool(os.environ.get("WT_SESSION"))


@functools.cache
def has_chafa() -> bool:
    """True if chafa is available for thumbnail rendering (cached per process)."""
    import shutil
    if shutil.which("chafa"):
        return True
    if IS_WINDOWS:
        # chafa via winget installs into a versioned subdirectory under WinGet packages
        winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_base.is_dir():
            for pkg_dir in winget_base.iterdir():
                if pkg_dir.name.startswith("hpjansson.Chafa"):
                    for chafa_exe in pkg_dir.rglob("chafa.exe"):
                        return True
    return False


@functools.cache
def get_chafa_exe() -> str | None:
    """Return the chafa executable path, probing winget install dirs on Windows (cached per process)."""
    import shutil
    found = shutil.which("chafa")
    if found:
        return found
    if IS_WINDOWS:
        winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_base.is_dir():
            for pkg_dir in winget_base.iterdir():
                if pkg_dir.name.startswith("hpjansson.Chafa"):
                    for chafa_exe in pkg_dir.rglob("chafa.exe"):
                        return str(chafa_exe)
    return None


def download_thumbnail(url: str, dest: str, timeout: int = 8) -> bool:
    """Download a file using Python stdlib urllib (cross-platform, no subprocess).

    Tries verified SSL first, falls back to unverified on certificate errors
    (common on corporate networks with MITM proxies). Thumbnail images are
    public CDN content so skipping verification is acceptable as a fallback.
    Returns True on success.
    """
    import ssl
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    for ctx in (_ssl_context_verified(), _ssl_context_unverified()):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read()
            if len(data) < 100:
                return False
            Path(dest).write_bytes(data)
            return True
        except ssl.SSLError:
            continue
        except ssl.SSLCertVerificationError:
            continue
        except urllib.error.URLError as e:
            if "SSL" in str(e) or "certificate" in str(e).lower():
                continue
            return False
        except Exception:
            return False
    return False


def _ssl_context_verified():
    import ssl
    return ssl.create_default_context()


def _ssl_context_unverified():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Unified Process Registry ──────────────────────────────────────────────────

import subprocess
import threading


class ProcessRegistry:
    """Global registry of all child processes spawned by TermTube.

    Tracks mpv (audio/video), yt-dlp, chafa, and any other subprocesses so they
    can all be killed on exit — regardless of exit path (normal quit, Ctrl+C,
    SIGTERM, os._exit failsafe).
    """

    _instance: "ProcessRegistry | None" = None

    def __init__(self) -> None:
        self._procs: set[subprocess.Popen] = set()  # type: ignore[type-arg]
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "ProcessRegistry":
        """Return the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        """Add a subprocess to the registry."""
        with self._lock:
            self._procs.add(proc)

    def unregister(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        """Remove a subprocess from the registry (e.g. after it exits normally)."""
        with self._lock:
            self._procs.discard(proc)

    def kill_all(self, timeout: float = 2.0) -> int:
        """Kill every tracked subprocess. Returns count of processes killed.

        Sends SIGTERM first, waits up to timeout, then SIGKILL for stragglers.
        """
        import time

        with self._lock:
            procs = list(self._procs)
            self._procs.clear()
        if not procs:
            return 0

        killed = 0
        for proc in procs:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    killed += 1
            except Exception:
                pass

        deadline = time.monotonic() + timeout
        for proc in procs:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                proc.wait(timeout=max(0.05, remaining / max(len(procs), 1)))
            except Exception:
                pass

        for proc in procs:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

        return killed

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for p in self._procs if p.poll() is None)


def reap_orphans() -> None:
    """Kill stale TermTube processes and remove stale IPC sockets on startup.

    Handles the case where a previous instance was SIGKILL'd or crashed without
    cleanup. Checks for orphaned mpv processes with TermTube-specific
    command-line patterns, and removes stale socket files.
    """
    import glob as _glob

    for pattern in ("/tmp/termtube-mpv*.sock",):
        for sock in _glob.glob(pattern):
            try:
                os.unlink(sock)
            except OSError:
                pass

    if IS_WINDOWS:
        return

    try:
        import signal
        result = subprocess.run(
            ["pgrep", "-f", "mpv.*termtube-mpv"],
            capture_output=True, text=True, timeout=3,
        )
        for pid_str in result.stdout.strip().split("\n"):
            if pid_str.strip():
                try:
                    os.kill(int(pid_str.strip()), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ── Install Hints ─────────────────────────────────────────────────────────────

_INSTALL_HINTS: dict[str, dict[str, str]] = {
    "yt-dlp": {
        "windows": "winget install yt-dlp.yt-dlp  (or: download from github.com/yt-dlp/yt-dlp-nightly-builds/releases)",
        "macos":   "brew install yt-dlp  (or: curl -fsSL https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp_macos -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp)",
        "linux":   "curl -fsSL https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp",
    },
    "deno": {
        "windows": "winget install DenoLand.Deno",
        "macos":   "brew install deno",
        "linux":   "curl -fsSL https://deno.land/install.sh | sh",
    },
    "mpv": {
        "windows": "re-run setup.ps1 (bundles standalone mpv)",
        "macos":   "brew install mpv",
        "linux":   "sudo apt install mpv",
    },
    "chafa": {
        "windows": "winget install hpjansson.Chafa",
        "macos":   "brew install chafa",
        "linux":   "sudo apt install chafa",
    },
    "ffmpeg": {
        "windows": "winget install Gyan.FFmpeg",
        "macos":   "brew install ffmpeg",
        "linux":   "sudo apt install ffmpeg",
    },
}


def install_hint(tool: str) -> str:
    """Return a user-friendly install command for the given tool on this platform."""
    hints = _INSTALL_HINTS.get(tool, {})
    if IS_WINDOWS:
        return hints.get("windows", f"Install {tool} manually")
    if IS_MACOS:
        return hints.get("macos", f"brew install {tool}")
    return hints.get("linux", f"sudo apt install {tool}")
