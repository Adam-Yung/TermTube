"""OS-specific logic: directories, mpv IPC paths, clipboard, subprocess handling. Other modules import from here."""

from __future__ import annotations

import errno
import glob
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from src.strings import text

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def get_config_dir() -> Path:
    """User configuration directory (~/.config/TermTube or %APPDATA%/TermTube)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "TermTube"


def get_deps_dir() -> Path:
    """Root directory for TermTube-managed dependencies (deno, ffmpeg, mpv)."""
    base = _local_appdata() if IS_WINDOWS else Path.home() / ".local"
    return base / "termtube-deps"


def get_deps_bin() -> Path:
    """Binary directory containing all TermTube-managed executables."""
    return get_deps_dir() / "bin"


def is_tool_installed(name: str) -> bool:
    """True if the tool exists in the managed bin dir. System PATH copies never count."""
    return (get_deps_bin() / (f"{name}.exe" if IS_WINDOWS else name)).exists()


def prune_dir(directory: Path, pattern: str, max_age_days: int | None, max_count: int) -> tuple[int, int]:
    """Delete files matching ``pattern`` older than ``max_age_days`` (if given), then the oldest beyond ``max_count``.

    Age is mtime. Returns ``(expired, capped)``.
    """
    cutoff = time.time() - max_age_days * 86400 if max_age_days is not None else None
    files: list[tuple[float, Path]] = []
    expired = 0
    for f in directory.glob(pattern):
        try:
            mtime = f.stat().st_mtime
            if cutoff is not None and mtime < cutoff:
                f.unlink(missing_ok=True)
                expired += 1
            else:
                files.append((mtime, f))
        except OSError:
            pass
    capped = max(0, len(files) - max_count)
    files.sort()
    for _, f in files[:capped]:
        f.unlink(missing_ok=True)
    return expired, capped


def atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a unique temp file in the same directory and ``os.replace``.

    Readers never see a partial file. The file is created private (0600). Raises after removing the temp file.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_cache_dir() -> Path:
    """Cache directory: ``$TERMTUBE_CACHE_DIR``, else ~/.cache/termtube or %LOCALAPPDATA%/TermTube/cache."""
    override = os.environ.get("TERMTUBE_CACHE_DIR")
    if override:
        return Path(override)
    if IS_WINDOWS:
        return _local_appdata() / "TermTube" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "termtube"


def get_log_dir() -> Path:
    """Log/temp directory under the system temp dir."""
    return Path(tempfile.gettempdir()) / "TermTube"


def private_dir(path: str | Path) -> Path:
    """Create ``path`` with mode 0700 if absent and return it; raise PermissionError if it cannot be trusted.

    A symlink, a non-directory or a foreign owner is refused (/tmp names are predictable); a loose mode is fixed.
    """
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if IS_WINDOWS:
        return path
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PermissionError(errno.EPERM, "is not a plain directory", str(path))
    if info.st_uid != os.getuid():
        raise PermissionError(errno.EPERM, "is owned by another user", str(path))
    if info.st_mode & 0o077:
        path.chmod(0o700)
    return path


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
    return os.path.join(private_dir(ipc_dir), f"{name}.sock")


def get_ipc_path() -> str:
    return _ipc_path("termtube-mpv")


def get_audio_ipc_path() -> str:
    return _ipc_path("termtube-mpv-audio")


def get_video_ipc_path() -> str:
    return _ipc_path("termtube-mpv-video")


def _clipboard_commands() -> list[list[str]]:
    """The clipboard programs to try, in order."""
    if IS_WINDOWS:
        return [["clip.exe"]]
    if IS_MACOS:
        return [["pbcopy"]]
    linux = (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])
    return [cmd for cmd in linux if shutil.which(cmd[0])]


def clipboard_copy(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success."""
    data = text.encode("utf-16le") if IS_WINDOWS else text.encode()
    for cmd in _clipboard_commands():
        try:
            subprocess.run(cmd, input=data, check=True, capture_output=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def get_popen_kwargs(*, headless: bool = False) -> dict:
    """Popen/run kwargs: new process group on Windows, plus no console window if headless."""
    if not IS_WINDOWS:
        return {}

    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if headless:
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags}


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


class ProcessRegistry:
    """Singleton set of child processes (mpv etc.) so every exit path can kill them."""

    _instance: ProcessRegistry | None = None

    def __init__(self) -> None:
        self._procs: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> ProcessRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.add(proc)

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)

    def kill_all(self, timeout: float = 2.0) -> int:
        """terminate() all tracked processes, wait up to timeout in total, kill stragglers. Returns how many."""
        with self._lock:
            procs = list(self._procs)
            self._procs.clear()
        if not procs:
            return 0
        killed = sum(_terminate_if_running(proc) for proc in procs)
        _wait_all(procs, timeout)
        for proc in procs:
            _kill_if_running(proc)
        return killed


def _terminate_if_running(proc: subprocess.Popen) -> bool:
    try:
        if proc.poll() is None:
            proc.terminate()
            return True
    except Exception:
        pass
    return False


def _wait_all(procs: list[subprocess.Popen], timeout: float) -> None:
    """Wait for each process in turn, all within one ``timeout``."""
    deadline = time.monotonic() + timeout
    for proc in procs:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            proc.wait(timeout=max(0.05, remaining / len(procs)))
        except Exception:
            pass


def _kill_if_running(proc: subprocess.Popen) -> None:
    try:
        if proc.poll() is None:
            proc.kill()
    except Exception:
        pass


def reap_orphans() -> None:
    """Startup: remove stale mpv sockets and SIGTERM mpv processes left by a crashed instance. No-op on Windows."""
    if IS_WINDOWS:
        return
    _remove_stale_sockets()
    _terminate_orphan_mpv()


def _remove_stale_sockets() -> None:
    ipc_dir = _unix_ipc_dir()
    if not os.path.isdir(ipc_dir):
        return
    for sock in glob.glob(os.path.join(ipc_dir, "termtube-mpv*.sock")):
        try:
            os.unlink(sock)
        except OSError:
            pass


def _terminate_orphan_mpv() -> None:
    try:
        result = subprocess.run(["pgrep", "-f", "mpv.*termtube-mpv"], capture_output=True, text=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    for line in result.stdout.split():
        _terminate_pid(line)


def _terminate_pid(text_pid: str) -> None:
    """SIGTERM the process ``text_pid`` names, unless it is this one."""
    try:
        pid = int(text_pid)
        if pid != os.getpid():
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, ValueError):
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
        "windows": text("plat.mpv_windows"),
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
        return hints.get("windows", text("plat.install_manually", tool=tool))
    if IS_MACOS:
        return hints.get("macos", f"brew install {tool}")
    return hints.get("linux", f"sudo apt install {tool}")
