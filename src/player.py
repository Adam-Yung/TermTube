"""mpv player interface with custom seek bindings and IPC support."""

from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from src import logger
from src.platform import IS_WINDOWS, get_ipc_path, get_subprocess_flags, cleanup_ipc

# ── Persistent IPC socket pool ────────────────────────────────────────────────
# Keyed by socket_path → socket.socket (Unix only).
# Windows named pipes don't support persistent connections so they stay
# connect-per-call.  Each entry is created on first use and reused until
# mpv closes the other end (EPIPE / ECONNRESET), at which point we reconnect.
_persistent_sockets: dict[str, socket.socket] = {}
_persistent_lock = threading.Lock()

# Per-socket-path locks for serializing IPC send/recv operations.
_ipc_locks: dict[str, threading.Lock] = {}
_ipc_locks_lock = threading.Lock()


def _get_ipc_lock(socket_path: str) -> threading.Lock:
    """Return (or create) a per-path lock for serializing IPC operations."""
    with _ipc_locks_lock:
        lock = _ipc_locks.get(socket_path)
        if lock is None:
            lock = threading.Lock()
            _ipc_locks[socket_path] = lock
        return lock


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

_temp_input_confs: set[str] = set()


def _write_input_conf() -> str:
    """Write input.conf to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, prefix="termtube-mpv-")
    f.write(_INPUT_CONF)
    f.flush()
    f.close()
    _temp_input_confs.add(f.name)
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
        # 1. TermTube's bundled standalone CLI mpv (installed by bootstrap.py)
        termtube_mpv = Path(localappdata) / "termtube-deps" / "bin" / "mpv.exe"
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

    # Check bundled mpv first (explicit path, not PATH-dependent)
    from src.bootstrap import get_deps_bin
    bundled_mpv = get_deps_bin() / ("mpv.exe" if IS_WINDOWS else "mpv")
    if bundled_mpv.exists():
        return str(bundled_mpv)
    # Fall back to PATH
    which_mpv = shutil.which("mpv")
    if which_mpv:
        return which_mpv
    if IS_WINDOWS:
        mpvnet_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "mpv.net"
        mpvnet = mpvnet_dir / "mpvnet.exe"
        if mpvnet.exists():
            return str(mpvnet)
    return None


def _mpv_available() -> bool:
    return _mpv_exe() is not None


# ── Public API ────────────────────────────────────────────────────────────────

# ── IPC helpers ───────────────────────────────────────────────────────────────

def _ipc_send_recv(data: bytes, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> bytes:
    """Low-level send/receive over the IPC transport (Unix socket or Windows named pipe)."""
    if IS_WINDOWS:
        return _ipc_send_recv_pipe(data, pipe_path=socket_path, timeout=timeout)
    return _ipc_send_recv_socket(data, socket_path=socket_path, timeout=timeout)


def _get_persistent_socket(socket_path: str, timeout: float) -> socket.socket | None:
    """Return (or create) a persistent Unix domain socket for socket_path."""
    with _persistent_lock:
        s = _persistent_sockets.get(socket_path)
        if s is not None:
            return s
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(socket_path)
            _persistent_sockets[socket_path] = s
            return s
        except (OSError, ConnectionRefusedError, FileNotFoundError):
            return None


def _drop_persistent_socket(socket_path: str) -> None:
    """Close and remove a stale persistent socket so the next call reconnects."""
    with _persistent_lock:
        s = _persistent_sockets.pop(socket_path, None)
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


def close_persistent_socket(socket_path: str) -> None:
    """Public API: close the persistent socket for socket_path (e.g. on track end)."""
    _drop_persistent_socket(socket_path)


def close_all_sockets() -> None:
    """Close all persistent IPC sockets and clean temp files (called on app exit)."""
    with _persistent_lock:
        for s in _persistent_sockets.values():
            try:
                s.close()
            except OSError:
                pass
        _persistent_sockets.clear()
    for path in list(_temp_input_confs):
        try:
            os.unlink(path)
        except OSError:
            pass
    _temp_input_confs.clear()


def _ipc_send_recv_socket(data: bytes, *, socket_path: str, timeout: float) -> bytes:
    """Unix domain socket transport — reuses a persistent connection."""
    lock = _get_ipc_lock(socket_path)
    with lock:
        for _attempt in range(2):
            s = _get_persistent_socket(socket_path, timeout)
            if s is None:
                return b""
            try:
                s.settimeout(timeout)
                s.sendall(data)
                buf = b""
                try:
                    while True:
                        chunk = s.recv(4096)
                        if not chunk:
                            raise OSError("connection closed")
                        buf += chunk
                        if b"\n" in buf:
                            break
                except socket.timeout:
                    pass
                return buf
            except (OSError, BrokenPipeError, ConnectionResetError):
                _drop_persistent_socket(socket_path)
                # second attempt will reconnect
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
        return _poll_audio_properties_batched_pipe(socket_path=socket_path)
    return _poll_audio_properties_batched(socket_path=socket_path)


def _poll_audio_properties_batched_pipe(
    *, socket_path: str
) -> tuple[float | None, float | None, bool]:
    """Windows: batch all three requests in one named-pipe session."""
    try:
        import pywintypes
        import win32file
        import win32pipe

        timeout_ms = 1000
        try:
            win32pipe.WaitNamedPipe(socket_path, timeout_ms)
        except pywintypes.error:
            pass

        try:
            handle = win32file.CreateFile(
                socket_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None,
            )
        except pywintypes.error:
            return None, None, False

        try:
            win32pipe.SetNamedPipeHandleState(
                handle, win32pipe.PIPE_READMODE_BYTE, None, None
            )
            # Write all 3 requests at once
            payload = b""
            for i, prop in enumerate(("time-pos", "duration", "pause")):
                payload += (json.dumps({"command": ["get_property", prop], "request_id": i}) + "\n").encode()
            win32file.WriteFile(handle, payload)

            # Read all 3 responses
            buf = b""
            results: dict[int, dict] = {}
            while len(results) < 3:
                try:
                    _, chunk = win32file.ReadFile(handle, 4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            resp = json.loads(line)
                            rid = resp.get("request_id")
                            if rid is not None:
                                results[rid] = resp
                        except json.JSONDecodeError:
                            pass
                except pywintypes.error:
                    break
            return _extract_poll_results(results)
        finally:
            win32file.CloseHandle(handle)
    except ImportError:
        # pywin32 not installed — fall back to sequential
        pos = get_ipc_property("time-pos", socket_path=socket_path)
        dur = get_ipc_property("duration", socket_path=socket_path)
        paused = get_ipc_property("pause", socket_path=socket_path)
        return (
            float(pos) if pos is not None else None,
            float(dur) if dur is not None else None,
            paused is True,
        )
    except Exception:
        return None, None, False


def _extract_poll_results(
    results: dict[int, dict],
) -> tuple[float | None, float | None, bool]:
    """Extract (time_pos, duration, is_paused) from batched IPC results."""
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


def _poll_audio_properties_batched(
    *, socket_path: str
) -> tuple[float | None, float | None, bool]:
    """Unix: batch all three requests on the persistent socket connection."""
    payload = b""
    for i, prop in enumerate(("time-pos", "duration", "pause")):
        payload += (
            json.dumps({"command": ["get_property", prop], "request_id": i}) + "\n"
        ).encode()

    lock = _get_ipc_lock(socket_path)
    with lock:
        for _attempt in range(2):
            s = _get_persistent_socket(socket_path, 1.0)
            if s is None:
                return None, None, False
            try:
                s.settimeout(1.0)
                s.sendall(payload)
                buf = b""
                results: dict[int, dict] = {}
                try:
                    while len(results) < 3:
                        chunk = s.recv(4096)
                        if not chunk:
                            raise OSError("connection closed")
                        buf += chunk
                        *complete_lines, buf = buf.split(b"\n")
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
                return _extract_poll_results(results)
            except (OSError, BrokenPipeError, ConnectionResetError):
                _drop_persistent_socket(socket_path)
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

