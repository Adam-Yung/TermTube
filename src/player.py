"""mpv launch helpers, the headless audio command, the launch loop and the IPC commands sent to a running mpv."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src import logger, mpv_ipc
from src.plat import IS_WINDOWS, ProcessRegistry, get_deps_bin, get_ipc_path, get_popen_kwargs, install_hint
from src.strings import text

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


# Keys in the mpv window of a playlist run: the exit code says what was asked. Later lines override earlier ones.
EXIT_NEXT, EXIT_PREV, EXIT_STOP = 10, 11, 12
_SEQUENCE_CONF = f"""\
> quit {EXIT_NEXT}
< quit {EXIT_PREV}
q quit {EXIT_STOP}
CLOSE_WIN quit {EXIT_STOP}
Meta+q quit {EXIT_STOP}
"""


def write_input_conf(*, sequence: bool = False) -> str:
    """Write input.conf to a temp file and return its path. ``sequence`` adds the playlist-run keys."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, prefix="termtube-mpv-")
    f.write(_INPUT_CONF + (_SEQUENCE_CONF if sequence else ""))
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


def _headless_windows_mpv() -> str | None:
    """The bundled mpv.exe, else a PATH one that is not mpv.net's shim."""
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
    return which if real else None


def mpv_exe(*, headless: bool = False) -> str | None:
    """Return the mpv executable path, or None.

    `headless=True` on Windows never returns mpv.net or its shim (they always open a window).
    """
    if headless and IS_WINDOWS:
        return _headless_windows_mpv()

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


def close_persistent_socket(socket_path: str) -> None:
    """Close the pooled socket for socket_path (call when a track ends)."""
    mpv_ipc.drop_socket(socket_path)


def close_all_sockets() -> None:
    """Close all pooled sockets and delete temp input.conf files (app exit)."""
    mpv_ipc.close_all()
    for path in list(_temp_input_confs):
        try:
            os.unlink(path)
        except OSError:
            pass
    _temp_input_confs.clear()


def send_ipc_command(cmd: dict, *, socket_path: str = IPC_SOCKET, timeout: float = 1.0) -> dict | None:
    """Send a JSON command to mpv; return the first parsed reply line or None."""
    if logger.is_debug():
        logger.debug("mpv ipc → %s @ %s", cmd.get("command", cmd), socket_path)
    payload = (json.dumps(cmd) + "\n").encode()
    data = mpv_ipc.send_recv(payload, socket_path=socket_path, timeout=timeout)
    for line in data.decode(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def poll_audio_properties(*, socket_path: str = IPC_SOCKET) -> mpv_ipc.PollResult:
    """Return (time_pos, duration, is_paused) from one batched IPC round trip."""
    return mpv_ipc.poll(socket_path=socket_path)


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
    ("could not open/read", "player.error_network"),
    ("http error 403", "player.error_denied"),
    ("http error 429", "player.error_rate_limited"),
    ("no video", "player.error_no_video"),
    ("no audio", "player.error_no_audio"),
    ("connection refused", "player.error_refused"),
    ("timed out", "player.error_timeout"),
    ("does not exist", "player.error_not_found"),
    ("drm", "player.error_drm"),
    ("login required", "player.error_login"),
    ("private video", "player.error_private"),
    ("age-restricted", "player.error_age"),
)


def friendly_mpv_error(raw: str) -> str:
    """Map mpv or yt-dlp stderr to a short message; unknown text is truncated to 100 characters."""
    lower = raw.lower()
    for pattern, friendly in _MPV_ERROR_HINTS:
        if pattern in lower:
            return text(friendly)
    return raw[:100]


def start_args(start: float | None) -> list[str]:
    """mpv flag that starts playback ``start`` seconds in; the one place both players add it."""
    return [f"--start={int(start)}"] if start else []


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
    start: float | None = None,
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
    cmd += start_args(start)
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
    """How the loop ended: ``ok`` (exit 0, 4, run codes), ``killed`` (3), ``stale``, ``failed`` or ``launch_error``."""

    status: str
    returncode: int | None = None
    stderr: str = ""
    message: str = ""


def _spawn(cmd: list[str], *, headless: bool, capture_stderr: bool) -> subprocess.Popen | MpvOutcome:
    """Start mpv; a ``launch_error`` outcome when it cannot be started."""
    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
            text=capture_stderr,
            encoding="utf-8" if capture_stderr else None,
            errors="replace" if capture_stderr else None,
            **get_popen_kwargs(headless=headless),
        )
    except FileNotFoundError:
        return MpvOutcome("launch_error", message=text("player.mpv_missing", hint=install_hint("mpv")))
    except OSError as exc:
        return MpvOutcome("launch_error", message=text("player.launch_failed", error=exc))


def _wait_for_exit(proc: subprocess.Popen) -> str:
    """Block until mpv exits, then unregister it. Returns its captured stderr, stripped."""
    try:
        _, err = proc.communicate()
    except Exception:
        err = ""
    finally:
        ProcessRegistry.get().unregister(proc)
    return (err or "").strip()


def _normal_exit(returncode: int | None) -> str | None:
    """The outcome status of an exit that is not retried, or None for an abnormal one."""
    if returncode in (_EXIT_EOF, _EXIT_QUIT, EXIT_NEXT, EXIT_PREV, EXIT_STOP):
        return "ok"
    if returncode == _EXIT_SIGNAL:
        return "killed"
    return None


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
        proc = _spawn(build_cmd(attempt), headless=headless, capture_stderr=capture_stderr)
        if isinstance(proc, MpvOutcome):
            return proc
        ProcessRegistry.get().register(proc)
        if on_spawn:
            on_spawn(proc, attempt)
        stderr = _wait_for_exit(proc)
        if is_stale():
            return MpvOutcome("stale", proc.returncode, stderr)
        status = _normal_exit(proc.returncode)
        if status:
            return MpvOutcome(status, proc.returncode, stderr)
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
