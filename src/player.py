"""mpv launch helpers and JSON IPC client (Unix socket, Windows named pipe)."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src import logger
from src.plat import IS_WINDOWS, ProcessRegistry, get_deps_bin, get_ipc_path, get_popen_kwargs, install_hint

_persistent_sockets: dict[str, socket.socket] = {}
_persistent_lock = threading.Lock()

_ipc_locks: dict[str, threading.Lock] = {}
_ipc_locks_lock = threading.Lock()


_IPC_LOCKS_MAX = 20


def _get_ipc_lock(socket_path: str) -> threading.Lock:
    """Return the lock that serializes send/recv on one socket path."""
    with _ipc_locks_lock:
        lock = _ipc_locks.get(socket_path)
        if lock is None:
            if len(_ipc_locks) >= _IPC_LOCKS_MAX:
                _ipc_locks.clear()
            lock = threading.Lock()
            _ipc_locks[socket_path] = lock
        return lock


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


def write_input_conf() -> str:
    """Write input.conf to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, prefix="termtube-mpv-")
    f.write(_INPUT_CONF)
    f.flush()
    f.close()
    _temp_input_confs.add(f.name)
    return f.name


def _is_real_cli_mpv(path: str) -> bool:
    """Return True unless `path` is mpv.net's `mpv.exe` shim (detected by a sibling `mpvnet.exe`)."""
    if not IS_WINDOWS:
        return True
    try:
        parent = Path(path).resolve().parent
        return not (parent / "mpvnet.exe").exists()
    except Exception:
        return True


def mpv_exe(*, headless: bool = False) -> str | None:
    """Return the mpv executable path, or None.

    `headless=True` on Windows never returns mpv.net or its shim (they always open a window).
    """
    if headless and IS_WINDOWS:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        termtube_mpv = Path(localappdata) / "termtube-deps" / "bin" / "mpv.exe"
        exists = termtube_mpv.exists()
        logger.debug(
            "mpv probe: LOCALAPPDATA=%r bundled=%s exists=%s",
            localappdata, str(termtube_mpv), exists,
        )
        if exists:
            return str(termtube_mpv)
        which = shutil.which("mpv")
        real = bool(which) and _is_real_cli_mpv(which)
        logger.debug("mpv probe: shutil.which=%r real_cli=%s", which, real)
        if which and real:
            return which
        return None

    bundled_mpv = get_deps_bin() / ("mpv.exe" if IS_WINDOWS else "mpv")
    if bundled_mpv.exists():
        return str(bundled_mpv)
    which_mpv = shutil.which("mpv")
    if which_mpv:
        return which_mpv
    if IS_WINDOWS:
        mpvnet_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "mpv.net"
        mpvnet = mpvnet_dir / "mpvnet.exe"
        if mpvnet.exists():
            return str(mpvnet)
    return None


def _ipc_send_recv(data: bytes, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> bytes:
    """Send bytes and return the first reply chunk(s) over the platform transport; b"" on failure."""
    if IS_WINDOWS:
        return _ipc_send_recv_pipe(data, pipe_path=socket_path, timeout=timeout)
    return _ipc_send_recv_socket(data, socket_path=socket_path, timeout=timeout)


def _get_persistent_socket(socket_path: str, timeout: float) -> socket.socket | None:
    """Return the pooled socket for socket_path, connecting on first use; None if mpv is not listening."""
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
    """Close and forget the pooled socket so the next call reconnects."""
    with _persistent_lock:
        s = _persistent_sockets.pop(socket_path, None)
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
    with _ipc_locks_lock:
        _ipc_locks.pop(socket_path, None)


def close_persistent_socket(socket_path: str) -> None:
    """Close the pooled socket for socket_path (call when a track ends)."""
    _drop_persistent_socket(socket_path)


def close_all_sockets() -> None:
    """Close all pooled sockets and delete temp input.conf files (app exit)."""
    with _persistent_lock:
        for s in _persistent_sockets.values():
            try:
                s.close()
            except OSError:
                pass
        _persistent_sockets.clear()
    with _ipc_locks_lock:
        _ipc_locks.clear()
    for path in list(_temp_input_confs):
        try:
            os.unlink(path)
        except OSError:
            pass
    _temp_input_confs.clear()


def _ipc_send_recv_socket(data: bytes, *, socket_path: str, timeout: float) -> bytes:
    """Unix transport on the pooled socket; one reconnect retry after a broken pipe."""
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
                except TimeoutError:
                    pass
                return buf
            except (OSError, BrokenPipeError, ConnectionResetError):
                _drop_persistent_socket(socket_path)
        return b""


def _ipc_send_recv_pipe(data: bytes, *, pipe_path: str, timeout: float) -> bytes:
    """Windows named-pipe transport (pywin32), connect-per-call; b"" if pywin32 or the pipe is missing."""
    try:
        import pywintypes
        import win32file
        import win32pipe

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
    """Send a JSON command to mpv; return the first parsed reply line or None."""
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
    """Return an mpv property value, or None on any failure."""
    resp = send_ipc_command({"command": ["get_property", prop]}, socket_path=socket_path)
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def poll_audio_properties(
    *, socket_path: str = IPC_SOCKET
) -> tuple[float | None, float | None, bool]:
    """Return (time_pos, duration, is_paused) from one batched IPC round trip."""
    if IS_WINDOWS:
        return _poll_audio_properties_batched_pipe(socket_path=socket_path)
    return _poll_audio_properties_batched(socket_path=socket_path)


_POLL_PROPS = ("time-pos", "duration", "pause")


def _poll_payload() -> bytes:
    return b"".join(
        (json.dumps({"command": ["get_property", prop], "request_id": i}) + "\n").encode()
        for i, prop in enumerate(_POLL_PROPS)
    )


def _collect_replies(buf: bytes, results: dict[int, dict]) -> bytes:
    """Parse complete lines in buf into results by request_id; return the unfinished tail."""
    *lines, tail = buf.split(b"\n")
    for raw in lines:
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            continue
        rid = resp.get("request_id") if isinstance(resp, dict) else None
        if rid is not None:
            results[rid] = resp
    return tail


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
            win32file.WriteFile(handle, _poll_payload())
            buf = b""
            results: dict[int, dict] = {}
            while len(results) < len(_POLL_PROPS):
                try:
                    _, chunk = win32file.ReadFile(handle, 4096)
                except pywintypes.error:
                    break
                if not chunk:
                    break
                buf = _collect_replies(buf + chunk, results)
            return _extract_poll_results(results)
        finally:
            win32file.CloseHandle(handle)
    except ImportError:
        return _extract_poll_results(
            {i: {"error": "success", "data": get_ipc_property(prop, socket_path=socket_path)}
             for i, prop in enumerate(_POLL_PROPS)}
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
    payload = _poll_payload()
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
                    while len(results) < len(_POLL_PROPS):
                        chunk = s.recv(4096)
                        if not chunk:
                            raise OSError("connection closed")
                        buf = _collect_replies(buf + chunk, results)
                except TimeoutError:
                    pass
                return _extract_poll_results(results)
            except (OSError, BrokenPipeError, ConnectionResetError):
                _drop_persistent_socket(socket_path)
        return None, None, False


def cookie_args_to_ytdl_raw(cookie_args: list[str]) -> str:
    """yt-dlp flags to mpv `--ytdl-raw-options`: ['--cookies-from-browser', 'x'] -> 'cookies-from-browser=x'."""
    opts: list[str] = []
    i = 0
    while i < len(cookie_args):
        arg = cookie_args[i]
        if arg.startswith("--") and i + 1 < len(cookie_args) and not cookie_args[i + 1].startswith("--"):
            key = arg[2:]
            val = cookie_args[i + 1]
            opts.append(f"{key}={val}")
            i += 2
        else:
            i += 1
    return ",".join(opts)


_MPV_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    ("could not open/read", "Network error — video unavailable or region-blocked"),
    ("http error 403", "Access denied — check browser authentication in Settings"),
    ("http error 429", "Rate limited by YouTube — wait a moment and try again"),
    ("no video", "No playable video stream found"),
    ("no audio", "No playable audio stream found"),
    ("connection refused", "Network connection failed"),
    ("timed out", "Connection timed out"),
    ("does not exist", "Video not found or deleted"),
    ("drm", "DRM-protected content cannot be played"),
    ("login required", "Video requires login — set a browser in Settings"),
    ("private video", "This video is private"),
    ("age-restricted", "Age-restricted — browser authentication required"),
)


def friendly_mpv_error(raw: str) -> str:
    """Map mpv or yt-dlp stderr to a short message; unknown text is truncated to 100 characters."""
    lower = raw.lower()
    for pattern, friendly in _MPV_ERROR_HINTS:
        if pattern in lower:
            return friendly
    return raw[:100]


def audio_command(
    exe: str,
    *,
    input_conf: str,
    socket_path: str,
    title: str = "",
    stream_url: str | None = None,
    page_url: str = "",
    ytdl_format: str = "",
    cookie_args: list[str] | None = None,
    mpv_log: str | None = None,
) -> list[str]:
    """Build the headless mpv command for background audio. ``mpv_log`` makes mpv write a verbose log file there.

    With ``stream_url`` mpv plays it directly. Without one, mpv resolves ``page_url``
    itself through its yt-dlp hook, using ``ytdl_format`` and the cookie options.
    """
    cmd = [
        exe,
        f"--input-conf={input_conf}",
        f"--input-ipc-server={socket_path}",
        "--no-video",
        "--force-window=no",
        "--no-input-terminal",
        "--msg-level=all=error",
        "--cache=yes",
        "--demuxer-max-bytes=150M",
        "--demuxer-readahead-secs=30",
    ]
    if title:
        cmd += [f"--title={title}", f"--force-media-title={title}"]
    if mpv_log:
        cmd += ["--msg-level=all=info", f"--log-file={mpv_log}"]
    if stream_url:
        return cmd + ["--no-ytdl", "--", stream_url]
    cmd.append(f"--ytdl-format={ytdl_format or 'ba/b'}")
    raw = cookie_args_to_ytdl_raw(cookie_args or [])
    if raw:
        cmd.append(f"--ytdl-raw-options={raw}")
    return cmd + ["--", page_url]


# mpv exit codes: 0 end of file, 3 killed by a signal, 4 quit by command.
_EXIT_EOF, _EXIT_SIGNAL, _EXIT_QUIT = 0, 3, 4
MPV_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class MpvOutcome:
    """How the loop ended: ``ok`` (exit 0 or 4), ``killed`` (3), ``stale``, ``failed`` or ``launch_error``."""

    status: str
    returncode: int | None = None
    stderr: str = ""
    message: str = ""


def run_mpv_with_retries(
    build_cmd: Callable[[int], list[str]],
    *,
    headless: bool,
    is_stale: Callable[[], bool],
    on_spawn: Callable[[subprocess.Popen, int], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
    capture_stderr: bool = False,
    max_attempts: int = MPV_MAX_ATTEMPTS,
    retry_delay: float = 1.0,
) -> MpvOutcome:
    """Run mpv to completion, relaunching after an abnormal exit. Blocks the calling worker thread.

    ``build_cmd(attempt)`` returns the command line; later attempts should re-resolve an expired stream URL.
    ``is_stale`` is checked before each launch and after each exit. ``on_spawn`` runs once the process is
    registered with ``ProcessRegistry``; the process is unregistered when it exits.
    """
    for attempt in range(1, max_attempts + 1):
        if is_stale():
            return MpvOutcome("stale")
        try:
            proc = subprocess.Popen(
                build_cmd(attempt),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
                text=capture_stderr,
                encoding="utf-8" if capture_stderr else None,
                errors="replace" if capture_stderr else None,
                **get_popen_kwargs(headless=headless),
            )
        except FileNotFoundError:
            return MpvOutcome("launch_error", message=f"mpv not found — install with: {install_hint('mpv')}")
        except OSError as exc:
            return MpvOutcome("launch_error", message=f"Failed to launch mpv: {exc}")
        ProcessRegistry.get().register(proc)
        if on_spawn:
            on_spawn(proc, attempt)
        try:
            _, err = proc.communicate()
        except Exception:
            err = ""
        finally:
            ProcessRegistry.get().unregister(proc)
        stderr = (err or "").strip()
        if is_stale():
            return MpvOutcome("stale", proc.returncode, stderr)
        if proc.returncode in (_EXIT_EOF, _EXIT_QUIT):
            return MpvOutcome("ok", proc.returncode, stderr)
        if proc.returncode == _EXIT_SIGNAL:
            return MpvOutcome("killed", proc.returncode, stderr)
        if attempt == max_attempts:
            logger.warning(
                "mpv failed after %d attempts (rc=%s): %s",
                max_attempts, proc.returncode, stderr or "(no stderr output)",
            )
            return MpvOutcome("failed", proc.returncode, stderr)
        logger.debug("mpv retry %d/%d (rc=%s)", attempt, max_attempts, proc.returncode)
        if on_retry:
            on_retry(attempt)
        time.sleep(retry_delay)
    return MpvOutcome("failed")
