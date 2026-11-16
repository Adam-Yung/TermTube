"""OS-specific logic: directories, mpv IPC paths, clipboard, subprocess handling. Other modules import from here."""

from __future__ import annotations

import glob
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")



def get_config_dir() -> Path:
    """User configuration directory (~/.config/TermTube or %APPDATA%/TermTube)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "TermTube"


def get_deps_dir() -> Path:
    """Root directory for TermTube-managed dependencies (deno, ffmpeg, mpv)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local"
    return base / "termtube-deps"


def get_deps_bin() -> Path:
    """Binary directory containing all TermTube-managed executables."""
    return get_deps_dir() / "bin"


def is_tool_installed(name: str) -> bool:
    """True if the tool exists in the managed bin dir. System PATH copies never count."""
    return (get_deps_bin() / (f"{name}.exe" if IS_WINDOWS else name)).exists()


def get_cache_dir() -> Path:
    """Cache directory (~/.cache/termtube or %LOCALAPPDATA%/TermTube/cache)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "TermTube" / "cache"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "termtube"


def get_log_dir() -> Path:
    """Log/temp directory under the system temp dir."""
    return Path(tempfile.gettempdir()) / "TermTube"




def _unix_ipc_dir() -> str:
    """Per-user directory for IPC sockets."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return runtime_dir
    return f"/tmp/termtube-{os.getuid()}"


def _ipc_path(name: str) -> str:
    """Named pipe on Windows; socket in a 0700 per-user directory elsewhere."""
    if IS_WINDOWS:
        return rf"\\.\pipe\{name}"
    ipc_dir = _unix_ipc_dir()
    os.makedirs(ipc_dir, mode=0o700, exist_ok=True)
    return os.path.join(ipc_dir, f"{name}.sock")


def get_ipc_path() -> str:
    return _ipc_path("termtube-mpv")


def get_audio_ipc_path() -> str:
    return _ipc_path("termtube-mpv-audio")


def get_video_ipc_path() -> str:
    return _ipc_path("termtube-mpv-video")


def clipboard_copy(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success."""
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




def get_subprocess_flags(*, headless: bool = False) -> dict:
    """Popen/run kwargs: new process group on Windows, plus no console window if headless."""
    if not IS_WINDOWS:
        return {}

    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if headless:
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags}


def get_popen_kwargs(*, headless: bool = False) -> dict:
    """Alias of get_subprocess_flags."""
    return get_subprocess_flags(headless=headless)


def terminate_process(proc, *, timeout: float = 3.0) -> None:
    """terminate(), wait up to timeout, then kill(). Accepts None."""
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
    """Unlink a Unix socket file. Windows pipes vanish with their last handle."""
    if IS_WINDOWS:
        return
    try:
        os.unlink(ipc_path)
    except OSError:
        pass




def download_thumbnail(url: str, dest: str, timeout: int = 8) -> bool:
    """Fetch a thumbnail to dest. True on success.

    Retries without certificate verification after an SSL failure (MITM proxies on corporate
    networks). Acceptable only because thumbnails are public CDN images; never reuse for anything else.
    """
    import ssl
    import urllib.error
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


class ProcessRegistry:
    """Singleton set of child processes (mpv etc.) so every exit path can kill them."""

    _instance: ProcessRegistry | None = None

    def __init__(self) -> None:
        self._procs: set[subprocess.Popen] = set()  # type: ignore[type-arg]
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> ProcessRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        with self._lock:
            self._procs.add(proc)

    def unregister(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        with self._lock:
            self._procs.discard(proc)

    def kill_all(self, timeout: float = 2.0) -> int:
        """terminate() all tracked processes, wait up to timeout in total, kill stragglers. Returns how many."""
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


def reap_orphans() -> None:
    """Startup: remove stale mpv sockets and SIGTERM mpv processes left by a crashed instance."""
    ipc_dir = _unix_ipc_dir()
    if os.path.isdir(ipc_dir):
        for sock in glob.glob(os.path.join(ipc_dir, "termtube-mpv*.sock")):
            try:
                os.unlink(sock)
            except OSError:
                pass

    if IS_WINDOWS:
        return

    try:
        my_pid = os.getpid()
        result = subprocess.run(
            ["pgrep", "-f", "mpv.*termtube-mpv"],
            capture_output=True, text=True, timeout=3,
        )
        for pid_str in result.stdout.strip().split("\n"):
            pid_str = pid_str.strip()
            if not pid_str:
                continue
            try:
                pid = int(pid_str)
                if pid == my_pid:
                    continue
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


_INSTALL_HINTS: dict[str, dict[str, str]] = {
    "yt-dlp": {os_name: "python -m pip install -U yt-dlp  (inside TermTube's venv; it is a library, not a binary)"
               for os_name in ("windows", "macos", "linux")},
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
    "ffmpeg": {
        "windows": "winget install Gyan.FFmpeg",
        "macos":   "brew install ffmpeg",
        "linux":   "sudo apt install ffmpeg",
    },
}


def install_hint(tool: str) -> str:
    hints = _INSTALL_HINTS.get(tool, {})
    if IS_WINDOWS:
        return hints.get("windows", f"Install {tool} manually")
    if IS_MACOS:
        return hints.get("macos", f"brew install {tool}")
    return hints.get("linux", f"sudo apt install {tool}")
