"""mpv player interface with custom seek bindings and IPC support."""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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

def play(
    url: str,
    *,
    audio_only: bool = False,
    player: str = "mpv",
    title: str = "",
) -> None:
    """
    Stream video/audio URL with the configured player.
    Blocks until playback ends.
    """
    if player == "vlc" and _vlc_available():
        _play_vlc(url, audio_only=audio_only)
    elif _mpv_available():
        _play_mpv(url, audio_only=audio_only, title=title)
    else:
        raise RuntimeError("No supported player found. Install mpv: brew install mpv")


def play_local(path: str, *, audio_only: bool = False, player: str = "mpv", title: str = "") -> None:
    """Play a local file."""
    play(path, audio_only=audio_only, player=player, title=title)


# ── mpv ───────────────────────────────────────────────────────────────────────

def _play_mpv(url: str, *, audio_only: bool = False, title: str = "") -> None:
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
        # For video mode, mpv handles its own window — no extra flags needed

        if title:
            cmd += [f"--title={title}"]

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
