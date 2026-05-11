"""Platform abstraction layer for TermTube.

Centralises all OS-specific logic: paths, IPC, process management, clipboard,
and capability detection. Every other module should import from here rather than
doing ad-hoc platform checks.
"""

from __future__ import annotations

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


def get_data_dir() -> Path:
    """Application data directory (~/.local/share/TermTube or %LOCALAPPDATA%/TermTube)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
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


def has_chafa() -> bool:
    """True if chafa is available for thumbnail rendering."""
    import shutil
    return shutil.which("chafa") is not None


def has_curl() -> bool:
    """True if curl is available for thumbnail downloads."""
    import shutil
    return shutil.which("curl") is not None


def get_thumbnail_download_cmd(url: str, dest: str) -> list[str]:
    """Return the command to download a thumbnail.

    Uses curl on Unix, and curl (shipped with Windows 10+) or PowerShell fallback.
    """
    if IS_WINDOWS and not has_curl():
        return [
            "powershell", "-NoProfile", "-Command",
            f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}' -TimeoutSec 8",
        ]
    return ["curl", "-s", "-L", "--max-time", "8", "-o", dest, url]
