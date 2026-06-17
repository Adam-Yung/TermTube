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
from src.platform import IS_WINDOWS, get_ipc_path, get_subprocess_flags, cleanup_ipc

# Custom mpv input.conf — loaded for every playback session
_INPUT_CONF = """\
# TermTube seek bindings
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

IPC_SOCKET = get_ipc_path()


def _write_input_conf() -> str:
    """Write input.conf to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, prefix="termtube-mpv-")
    f.write(_INPUT_CONF)
    f.flush()
    f.close()
    return f.name


def _is_real_cli_mpv(path: str) -> bool:
    """Return True if `path` is the real upstream mpv CLI (not mpv.net's shim).

    mpv.net ships an `mpv.exe` in its install directory that is a stub
    redirecting to `mpvnet.exe` — which ALWAYS opens a GUI window even with
    `--force-window=no`. Detect that case by checking the parent directory
    for `mpvnet.exe`.
    """
    if not IS_WINDOWS:
        return True
    try:
        from pathlib import Path
        parent = Path(path).resolve().parent
        return not (parent / "mpvnet.exe").exists()
    except Exception:
        return True


def _mpv_exe(*, headless: bool = False) -> str | None:
    """Return the mpv executable path.

    Args:
        headless: If True on Windows, REQUIRE a standalone mpv.exe (no GUI
                  window). Will not fall back to mpv.net or its `mpv.exe`
                  shim — those always open a GUI window even with
                  `--force-window=no` and `--no-video`.
    """
    if headless and IS_WINDOWS:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        # 1. TermTube's bundled standalone CLI mpv (installed by setup.ps1)
        termtube_mpv = Path(localappdata) / "TermTube" / "mpv" / "mpv.exe"
        exists = termtube_mpv.exists()
        logger.debug(
            "mpv probe: LOCALAPPDATA=%r bundled=%s exists=%s",
            localappdata, str(termtube_mpv), exists,
        )
        if exists:
            return str(termtube_mpv)
        # 2. PATH mpv, but only if it's not mpv.net's shim
        which = shutil.which("mpv")
        real = bool(which) and _is_real_cli_mpv(which)
        logger.debug("mpv probe: shutil.which=%r real_cli=%s", which, real)
        if which and real:
            return which
        # 3. No headless-capable mpv. Return None so the caller surfaces a
        #    clear "install standalone mpv" error rather than silently
        #    spawning mpvnet (which pops a window).
        return None

    if shutil.which("mpv"):
        return "mpv"
    if IS_WINDOWS:
        mpvnet_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "mpv.net"
        mpvnet = mpvnet_dir / "mpvnet.exe"
        if mpvnet.exists():
            return str(mpvnet)
    return None


def _mpv_available() -> bool:
    return _mpv_exe() is not None


def _vlc_available() -> bool:
    if shutil.which("vlc"):
        return True
    if IS_WINDOWS:
        vlc_win = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "VideoLAN" / "VLC" / "vlc.exe"
        return vlc_win.exists()
    return Path("/Applications/VLC.app/Contents/MacOS/VLC").exists()


def _vlc_path() -> str:
    if shutil.which("vlc"):
        return "vlc"
    if IS_WINDOWS:
        return str(Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "VideoLAN" / "VLC" / "vlc.exe")
    return "/Applications/VLC.app/Contents/MacOS/VLC"


# ── Public API ────────────────────────────────────────────────────────────────

# ── IPC helpers ───────────────────────────────────────────────────────────────

def _ipc_send_recv(data: bytes, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> bytes:
    """Low-level send/receive over the IPC transport (Unix socket or Windows named pipe)."""
    if IS_WINDOWS:
        return _ipc_send_recv_pipe(data, pipe_path=socket_path, timeout=timeout)
    return _ipc_send_recv_socket(data, socket_path=socket_path, timeout=timeout)


def _ipc_send_recv_socket(data: bytes, *, socket_path: str, timeout: float) -> bytes:
    """Unix domain socket transport."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        s.sendall(data)
        buf = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
        except socket.timeout:
            pass
        s.close()
        return buf
    except (OSError, ConnectionRefusedError, FileNotFoundError):
        return b""


def _ipc_send_recv_pipe(data: bytes, *, pipe_path: str, timeout: float) -> bytes:
    """Windows named pipe transport using pywin32.

    Handles ERROR_PIPE_BUSY with WaitNamedPipe retry, and reads responses
    until a newline-terminated JSON response is received.
    """
    try:
        import pywintypes
        import win32file
        import win32pipe

        # Wait for the pipe to become available (mpv may be processing another request)
        timeout_ms = int(timeout * 1000)
        try:
            win32pipe.WaitNamedPipe(pipe_path, timeout_ms)
        except pywintypes.error:
            pass  # Pipe may already be available; try CreateFile anyway

        try:
            handle = win32file.CreateFile(
                pipe_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None,
            )
        except pywintypes.error:
            return b""

        try:
            # Set pipe to message mode for cleaner reads
            win32pipe.SetNamedPipeHandleState(
                handle, win32pipe.PIPE_READMODE_BYTE, None, None
            )
            win32file.WriteFile(handle, data)
            buf = b""
            while True:
                try:
                    _, chunk = win32file.ReadFile(handle, 4096)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break
                except pywintypes.error:
                    break
            return buf
        finally:
            win32file.CloseHandle(handle)
    except ImportError:
        return b""
    except Exception:
        return b""


def send_ipc_command(cmd: dict, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> dict | None:
    """Send a JSON command to a running mpv IPC socket. Returns the response dict or None."""
    if logger.is_debug():
        logger.debug("mpv ipc → %s @ %s", cmd.get("command", cmd), socket_path)
    payload = (json.dumps(cmd) + "\n").encode()
    data = _ipc_send_recv(payload, socket_path=socket_path, timeout=timeout)
    if not data:
        return None
    for line in data.decode(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def get_ipc_property(prop: str, *, socket_path: str = IPC_SOCKET) -> Any:
    """Get an mpv property via IPC socket. Returns the value or None."""
    resp = send_ipc_command({"command": ["get_property", prop]}, socket_path=socket_path)
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def poll_audio_properties(
    *, socket_path: str = IPC_SOCKET
) -> tuple[float | None, float | None, bool]:
    """Return (time_pos, duration, is_paused) in a single IPC connection.

    Batches all three get_property requests into one connection lifecycle,
    reducing overhead from 3 connect/send/recv/close cycles to one.
    """
    if IS_WINDOWS:
        return _poll_audio_properties_sequential(socket_path=socket_path)
    return _poll_audio_properties_batched(socket_path=socket_path)


def _poll_audio_properties_sequential(
    *, socket_path: str
) -> tuple[float | None, float | None, bool]:
    """Fallback for Windows: three sequential IPC calls."""
    pos = get_ipc_property("time-pos", socket_path=socket_path)
    dur = get_ipc_property("duration", socket_path=socket_path)
    paused = get_ipc_property("pause", socket_path=socket_path)
    return (
        float(pos) if pos is not None else None,
        float(dur) if dur is not None else None,
        paused is True,
    )


def _poll_audio_properties_batched(
    *, socket_path: str
) -> tuple[float | None, float | None, bool]:
    """Unix: batch all three requests in one socket connection."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(socket_path)
        for i, prop in enumerate(("time-pos", "duration", "pause")):
            s.sendall(
                (json.dumps({"command": ["get_property", prop], "request_id": i}) + "\n").encode()
            )
        data = b""
        results: dict[int, dict] = {}
        try:
            while len(results) < 3:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                *complete_lines, data = data.split(b"\n")
                for raw in complete_lines:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        resp = json.loads(raw)
                        rid = resp.get("request_id")
                        if rid is not None:
                            results[rid] = resp
                    except json.JSONDecodeError:
                        pass
        except socket.timeout:
            pass
        s.close()

        def _val(rid: int) -> Any:
            r = results.get(rid, {})
            return r.get("data") if r.get("error") == "success" else None

        pos = _val(0)
        dur = _val(1)
        paused = _val(2)
        return (
            float(pos) if pos is not None else None,
            float(dur) if dur is not None else None,
            paused is True,
        )
    except (OSError, ConnectionRefusedError, FileNotFoundError):
        return None, None, False


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
    cookie_args: yt-dlp cookie flags (e.g. config.cookie_args())
                 passed to mpv's internal yt-dlp via --ytdl-raw-options so YouTube auth works.
    """
    if player == "vlc" and _vlc_available():
        _play_vlc(url, audio_only=audio_only)
    elif _mpv_available():
        _play_mpv(url, audio_only=audio_only, title=title, ytdl_format=ytdl_format,
                  cookie_args=cookie_args)
    else:
        from src.platform import install_hint
        raise RuntimeError(f"No supported player found. Install mpv: {install_hint('mpv')}")



# ── mpv ───────────────────────────────────────────────────────────────────────

def _play_mpv(url: str, *, audio_only: bool = False, title: str = "", ytdl_format: str = "",
              cookie_args: list[str] | None = None) -> None:
    exe = _mpv_exe(headless=audio_only)
    if not exe:
        from src.platform import install_hint
        raise RuntimeError(f"No supported player found. Install mpv: {install_hint('mpv')}")
    input_conf = _write_input_conf()
    try:
        cmd = [
            exe,
            f"--input-conf={input_conf}",
            f"--input-ipc-server={IPC_SOCKET}",
        ]

        if audio_only:
            cmd += [
                "--no-video",
                "--force-window=no",
                "--term-osd-bar",
                "--term-osd-bar-chars=[=  ]",
                "--term-playing-msg="
                    "\\n  \033[1m${media-title}\033[0m"
                    "\\n  \033[36m${time-pos} / ${duration}\033[0m"
                    "  [\033[33m${percent-pos}%\033[0m]"
                    "  \033[90mh/l ±5s  H/L ±10s  0-9 jump%  q quit\033[0m\\n",
            ]
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
        result = subprocess.run(cmd, **get_subprocess_flags(headless=audio_only))
        if result.returncode not in (0, 4):  # 4 = quit by user
            logger.warning("mpv exited with code %d", result.returncode)
    finally:
        try:
            os.unlink(input_conf)
        except OSError:
            pass
        cleanup_ipc(IPC_SOCKET)


# ── VLC ───────────────────────────────────────────────────────────────────────

def _play_vlc(url: str, *, audio_only: bool = False) -> None:
    cmd = [_vlc_path()]
    if audio_only:
        cmd += ["--no-video"]
    cmd += [url]
    logger.debug("vlc cmd: %s", " ".join(cmd))
    subprocess.run(cmd)
