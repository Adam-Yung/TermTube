"""Transport for mpv's JSON IPC: pooled Unix sockets, Windows named pipes, and the batched property poll.

Every failure ends as an empty reply or ``(None, None, False)``: a dead mpv is a normal state.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
from collections.abc import Callable, Iterator
from functools import partial
from typing import Any

from src.plat import IS_WINDOWS

_persistent_sockets: dict[str, socket.socket] = {}
_persistent_lock = threading.Lock()

_ipc_locks: dict[str, threading.Lock] = {}
_ipc_locks_lock = threading.Lock()


_IPC_LOCKS_MAX = 20
_POLL_TIMEOUT = 1.0

PollResult = tuple[float | None, float | None, bool]  # time_pos, duration, is_paused

_NOTHING_POLLED: PollResult = (None, None, False)


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


def _close_quietly(s: socket.socket) -> None:
    try:
        s.close()
    except OSError:
        pass


def drop_socket(socket_path: str) -> None:
    """Close and forget the pooled socket so the next call reconnects."""
    with _persistent_lock:
        s = _persistent_sockets.pop(socket_path, None)
        if s is not None:
            _close_quietly(s)
    with _ipc_locks_lock:
        _ipc_locks.pop(socket_path, None)


def close_all() -> None:
    """Close all pooled sockets and forget their locks."""
    with _persistent_lock:
        for s in _persistent_sockets.values():
            _close_quietly(s)
        _persistent_sockets.clear()
    with _ipc_locks_lock:
        _ipc_locks.clear()


def _on_socket(socket_path: str, timeout: float, talk: Callable[[socket.socket], Any]) -> Any:
    """Run ``talk`` on the pooled socket under the path's lock; one reconnect retry after a broken pipe.

    None when mpv is not listening or both attempts break.
    """
    with _get_ipc_lock(socket_path):
        for _attempt in range(2):
            s = _get_persistent_socket(socket_path, timeout)
            if s is None:
                return None
            try:
                s.settimeout(timeout)
                return talk(s)
            except (OSError, BrokenPipeError, ConnectionResetError):
                drop_socket(socket_path)
        return None


def _recv(s: socket.socket) -> bytes:
    chunk = s.recv(4096)
    if not chunk:
        raise OSError("connection closed")
    return chunk


def _exchange_line(s: socket.socket, data: bytes) -> bytes:
    """Send ``data`` and read until a newline or the timeout."""
    s.sendall(data)
    buf = b""
    try:
        while b"\n" not in buf:
            buf += _recv(s)
    except TimeoutError:
        pass
    return buf


@contextlib.contextmanager
def _pipe(pipe_path: str, timeout: float) -> Iterator[Any]:
    """An open handle to mpv's named pipe, or None if it cannot be opened. ImportError without pywin32."""
    import pywintypes
    import win32file
    import win32pipe

    try:
        win32pipe.WaitNamedPipe(pipe_path, int(timeout * 1000))
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
        yield None
        return

    try:
        win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_BYTE, None, None)
        yield handle
    finally:
        win32file.CloseHandle(handle)


def _pipe_chunks(handle) -> Iterator[bytes]:
    """Reads from the pipe until it is empty or broken."""
    import pywintypes
    import win32file

    while True:
        try:
            _, chunk = win32file.ReadFile(handle, 4096)
        except pywintypes.error:
            return
        if not chunk:
            return
        yield chunk


def _first_line_from(handle) -> bytes:
    buf = b""
    for chunk in _pipe_chunks(handle):
        buf += chunk
        if b"\n" in buf:
            break
    return buf


def _send_recv_pipe(data: bytes, *, pipe_path: str, timeout: float) -> bytes:
    """Windows named-pipe transport (pywin32), connect-per-call; b"" if pywin32 or the pipe is missing."""
    try:
        with _pipe(pipe_path, timeout) as handle:
            if handle is None:
                return b""
            import win32file

            win32file.WriteFile(handle, data)
            return _first_line_from(handle)
    except Exception:
        return b""


def send_recv(data: bytes, *, socket_path: str, timeout: float) -> bytes:
    """Send bytes and return the first reply chunk(s) over the platform transport; b"" on failure."""
    if IS_WINDOWS:
        return _send_recv_pipe(data, pipe_path=socket_path, timeout=timeout)
    reply = _on_socket(socket_path, timeout, lambda s: _exchange_line(s, data))
    return reply or b""


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


def _reply_value(results: dict[int, dict], request_id: int) -> Any:
    reply = results.get(request_id, {})
    return reply.get("data") if reply.get("error") == "success" else None


def _extract_poll_results(results: dict[int, dict]) -> PollResult:
    """Extract (time_pos, duration, is_paused) from batched IPC results."""
    pos, dur, paused = (_reply_value(results, i) for i in range(len(_POLL_PROPS)))
    return (
        float(pos) if pos is not None else None,
        float(dur) if dur is not None else None,
        paused is True,
    )


def _exchange_poll(s: socket.socket, socket_path: str) -> PollResult:
    s.sendall(_poll_payload())
    buf = b""
    results: dict[int, dict] = {}
    try:
        while len(results) < len(_POLL_PROPS):
            buf = _collect_replies(buf + _recv(s), results)
    except TimeoutError:
        # Late replies would answer the next poll, which reuses the request ids.
        drop_socket(socket_path)
    return _extract_poll_results(results)


def _poll_audio_properties_batched(*, socket_path: str) -> PollResult:
    """Unix: batch all three requests on the persistent socket connection."""
    return _on_socket(socket_path, _POLL_TIMEOUT, partial(_exchange_poll, socket_path=socket_path)) or _NOTHING_POLLED


def _poll_results_from(handle) -> PollResult:
    buf = b""
    results: dict[int, dict] = {}
    for chunk in _pipe_chunks(handle):
        buf = _collect_replies(buf + chunk, results)
        if len(results) >= len(_POLL_PROPS):
            break
    return _extract_poll_results(results)


def _poll_audio_properties_batched_pipe(*, socket_path: str) -> PollResult:
    """Windows: batch all three requests in one named-pipe session."""
    try:
        with _pipe(socket_path, 1.0) as handle:
            if handle is None:
                return _NOTHING_POLLED
            import win32file

            win32file.WriteFile(handle, _poll_payload())
            return _poll_results_from(handle)
    except Exception:
        return _NOTHING_POLLED


def poll(*, socket_path: str) -> PollResult:
    """(time_pos, duration, is_paused) from one batched round trip."""
    if IS_WINDOWS:
        return _poll_audio_properties_batched_pipe(socket_path=socket_path)
    return _poll_audio_properties_batched(socket_path=socket_path)
