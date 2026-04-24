"""mpv player interface with custom seek bindings and IPC support."""

from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src import logger

# Custom mpv input.conf — loaded for every playback session
_INPUT_CONF = """\
# MyYouTube seek bindings
0 seek 0 absolute-percent
1 seek 10 absolute-percent
2 seek 20 absolute-percent
3 seek 30 absolute-percent
4 seek 40 absolute-percent
5 seek 50 absolute-percent
6 seek 60 absolute-percent
7 seek 70 absolute-percent
8 seek 80 absolute-percent
9 seek 90 absolute-percent
h seek -5
l seek +5
H seek -10
L seek +10
LEFT seek -5
RIGHT seek +5
Ctrl+LEFT seek -10
Ctrl+RIGHT seek +10
q quit
"""

IPC_SOCKET = "/tmp/myt-mpv.sock"


def _write_input_conf() -> str:
    """Write input.conf to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, prefix="myt-mpv-")
    f.write(_INPUT_CONF)
    f.flush()
    f.close()
    return f.name


def _mpv_available() -> bool:
    return shutil.which("mpv") is not None


def _vlc_available() -> bool:
    return shutil.which("vlc") is not None or Path("/Applications/VLC.app/Contents/MacOS/VLC").exists()


def _vlc_path() -> str:
    if shutil.which("vlc"):
        return "vlc"
    return "/Applications/VLC.app/Contents/MacOS/VLC"


# ── Public API ────────────────────────────────────────────────────────────────

# ── IPC helpers ───────────────────────────────────────────────────────────────

def send_ipc_command(cmd: dict, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> dict | None:
    """Send a JSON command to a running mpv IPC socket. Returns the response dict or None."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        s.sendall((json.dumps(cmd) + "\n").encode())
        data = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        except socket.timeout:
            pass
        s.close()
        for line in data.decode(errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, ConnectionRefusedError, FileNotFoundError):
        pass
    return None


def get_ipc_property(prop: str, *, socket_path: str = IPC_SOCKET) -> Any:
    """Get an mpv property via IPC socket. Returns the value or None."""
    resp = send_ipc_command({"command": ["get_property", prop]}, socket_path=socket_path)
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def is_playing(*, socket_path: str = IPC_SOCKET) -> bool:
    """Return True if mpv is active and not paused."""
    paused = get_ipc_property("pause", socket_path=socket_path)
    return paused is False


def pause_toggle(*, socket_path: str = IPC_SOCKET) -> None:
    """Toggle pause in a running mpv instance."""
    send_ipc_command({"command": ["cycle", "pause"]}, socket_path=socket_path)


def seek_to(seconds: float, *, socket_path: str = IPC_SOCKET) -> None:
    """Seek to an absolute position in seconds."""
    send_ipc_command({"command": ["seek", seconds, "absolute"]}, socket_path=socket_path)


def set_volume(vol: int, *, socket_path: str = IPC_SOCKET) -> None:
    """Set playback volume (0–130)."""
    send_ipc_command({"command": ["set_property", "volume", vol]}, socket_path=socket_path)


def playlist_append(url: str, *, socket_path: str = IPC_SOCKET) -> None:
    """Append a URL to mpv's internal playlist without interrupting current playback."""
    send_ipc_command({"command": ["loadfile", url, "append"]}, socket_path=socket_path)


def playlist_next(*, socket_path: str = IPC_SOCKET) -> None:
    """Skip to the next item in mpv's playlist."""
    send_ipc_command({"command": ["playlist-next"]}, socket_path=socket_path)


def playlist_prev(*, socket_path: str = IPC_SOCKET) -> None:
    """Skip to the previous item in mpv's playlist."""
    send_ipc_command({"command": ["playlist-prev"]}, socket_path=socket_path)


def _cookie_args_to_ytdl_raw(cookie_args: list[str]) -> str:
    """
    Convert yt-dlp cookie flags to mpv --ytdl-raw-options format.
    e.g. ['--cookies', '/path/to/cookies.txt']  →  'cookies=/path/to/cookies.txt'
         ['--cookies-from-browser', 'chrome']    →  'cookies-from-browser=chrome'
    """
    opts: list[str] = []
    i = 0
    while i < len(cookie_args):
        arg = cookie_args[i]
        if arg.startswith("--") and i + 1 < len(cookie_args) and not cookie_args[i + 1].startswith("--"):
            key = arg[2:]          # strip leading '--'
            val = cookie_args[i + 1]
            opts.append(f"{key}={val}")
            i += 2
        else:
            i += 1
    return ",".join(opts)


def play_playlist(
    urls: list[str],
    *,
    audio_only: bool = False,
    title: str = "",
    ytdl_format: str = "",
    cookie_args: list[str] | None = None,
) -> None:
    """Play multiple URLs sequentially as an mpv playlist. Blocks until done."""
    if not urls:
        return
    if not _mpv_available():
        raise RuntimeError("No supported player found. Install mpv: brew install mpv")
    input_conf = _write_input_conf()
    try:
        cmd = [
            "mpv",
            f"--input-conf={input_conf}",
            f"--input-ipc-server={IPC_SOCKET}",
        ]
        if audio_only:
            cmd += ["--no-video", "--term-osd-bar"]
        if title:
            cmd += [f"--title={title}"]
        if ytdl_format:
            cmd += [f"--ytdl-format={ytdl_format}"]
        ytdl_raw = _cookie_args_to_ytdl_raw(cookie_args or [])
        if ytdl_raw:
            cmd += [f"--ytdl-raw-options={ytdl_raw}"]
        cmd += ["--"] + urls
        logger.debug("mpv playlist cmd: %s [+%d urls]", " ".join(cmd[:6]), len(urls))
        result = subprocess.run(cmd)
        if result.returncode not in (0, 4):
            logger.warning("mpv exited with code %d", result.returncode)
    finally:
        for path in (input_conf, IPC_SOCKET):
            try:
                os.unlink(path)
            except OSError:
                pass


def play(
    url: str,
    *,
    audio_only: bool = False,
    player: str = "mpv",
    title: str = "",
    ytdl_format: str = "",
    cookie_args: list[str] | None = None,
) -> None:
    """
    Stream video/audio URL with the configured player.
    Blocks until playback ends.
    cookie_args: yt-dlp cookie flags (e.g. config.cookie_args) passed to mpv's
                 internal yt-dlp via --ytdl-raw-options so YouTube auth works.
    """
    if player == "vlc" and _vlc_available():
        _play_vlc(url, audio_only=audio_only)
    elif _mpv_available():
        _play_mpv(url, audio_only=audio_only, title=title, ytdl_format=ytdl_format,
                  cookie_args=cookie_args)
    else:
        raise RuntimeError("No supported player found. Install mpv: brew install mpv")


def play_local(path: str, *, audio_only: bool = False, player: str = "mpv", title: str = "") -> None:
    """Play a local file."""
    play(path, audio_only=audio_only, player=player, title=title)


# ── mpv ───────────────────────────────────────────────────────────────────────

def _play_mpv(url: str, *, audio_only: bool = False, title: str = "", ytdl_format: str = "",
              cookie_args: list[str] | None = None) -> None:
    input_conf = _write_input_conf()
    try:
        cmd = [
            "mpv",
            f"--input-conf={input_conf}",
            f"--input-ipc-server={IPC_SOCKET}",
        ]

        if audio_only:
            cmd += [
                "--no-video",
                "--term-osd-bar",
                "--term-osd-bar-chars=[=  ]",
                "--term-playing-msg="
                    "\\n  \033[1m${media-title}\033[0m"
                    "\\n  \033[36m${time-pos} / ${duration}\033[0m"
                    "  [\033[33m${percent-pos}%\033[0m]"
                    "  \033[90mh/l ±5s  H/L ±10s  0-9 jump%  q quit\033[0m\\n",
            ]
        # Video mode: mpv opens its own window. Silence terminal output so
        # nothing bleeds into the Textual TUI running in the background.
        if not audio_only:
            cmd += ["--really-quiet", "--no-terminal"]

        if title:
            cmd += [f"--title={title}"]

        if ytdl_format:
            cmd += [f"--ytdl-format={ytdl_format}"]

        ytdl_raw = _cookie_args_to_ytdl_raw(cookie_args or [])
        if ytdl_raw:
            cmd += [f"--ytdl-raw-options={ytdl_raw}"]

        cmd += ["--", url]

        logger.debug("mpv cmd: %s", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode not in (0, 4):  # 4 = quit by user
            logger.warning("mpv exited with code %d", result.returncode)
    finally:
        try:
            os.unlink(input_conf)
        except OSError:
            pass
        try:
            os.unlink(IPC_SOCKET)
        except OSError:
            pass


# ── VLC ───────────────────────────────────────────────────────────────────────

def _play_vlc(url: str, *, audio_only: bool = False) -> None:
    cmd = [_vlc_path()]
    if audio_only:
        cmd += ["--no-video"]
    cmd += [url]
    logger.debug("vlc cmd: %s", " ".join(cmd))
    subprocess.run(cmd)
