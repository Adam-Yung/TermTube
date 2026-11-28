"""The launch thread of the audio controller: resolve the URL, run a headless mpv, retry, report how it ended."""

from __future__ import annotations

import functools
import os
import subprocess
from dataclasses import dataclass
from functools import partial

from src import logger, player, streams
from src.entries import Entry
from src.errors import SourceError
from src.local_files import is_local_id
from src.plat import IS_WINDOWS, get_audio_ipc_path, install_hint
from src.progress import start_offset
from src.strings import text
from src.tui.fmt import escape_markup, fmt_clock
from src.tui.urls import watch_url

_DEFAULT_AUDIO_FORMAT = "ba/b"


@functools.cache
def _socket_base() -> str:
    return get_audio_ipc_path()


def _socket_for(session: int) -> str:
    """IPC path unique to ``session``, so a dying mpv never answers for the next one."""
    base = _socket_base()
    if session <= 1:
        return base
    stem, ext = os.path.splitext(base)
    return f"{stem}-{session}{ext}"


def _mpv_log_path() -> str | None:
    """Beside the app's --debug log, so a failed mpv can explain itself. None unless --debug is on."""
    log = logger.log_file() if logger.is_debug() else None
    return str(log.with_name(f"{log.stem}-mpv.log")) if log else None


@dataclass
class _AudioCommand:
    """The mpv command for each launch attempt; a retry resolves the stream URL again."""

    config: object
    entry: Entry
    exe: str
    input_conf: str
    socket_path: str
    ytdl_format: str
    url: str | None
    start: float | None

    def __call__(self, attempt: int) -> list[str]:
        vid = self.entry.get("id", "")
        local = self.entry.get("_local_path")
        if attempt > 1 and vid and not local:
            fresh = streams.re_resolve(vid, self.config, self.ytdl_format or _DEFAULT_AUDIO_FORMAT)
            if fresh:
                self.url = fresh[0]
        cmd = player.audio_command(
            self.exe,
            input_conf=self.input_conf,
            socket_path=self.socket_path,
            title=self.entry.get("title", ""),
            stream_url=self.url,
            page_url=local or watch_url(vid),
            ytdl_format=self.ytdl_format,
            cookie_args=self.config.browser_cookie_args(),
            mpv_log=_mpv_log_path(),
            start=self.start,
        )
        logger.debug("audio mpv cmd: %s", " ".join(cmd))
        return cmd


class AudioLaunchMixin:
    """Everything ``AudioController`` runs on the ``audio-launch`` thread.

    Needs ``_app``, ``_session``, ``_proc``, ``log``, ``_stale``, ``_clear_pending``, ``_start_sponsorblock``,
    ``_stop_if_current``, ``_on_finished`` and ``_on_failed`` from the controller.
    """

    def _launch_worker(self, entry: Entry, session: int, ytdl_format: str) -> None:
        """Thread body. An exception here would otherwise vanish and leave the bar on "Buffering…" forever."""
        logger.debug("audio launch worker started (session %d)", session)
        try:
            self._launch(entry, session, ytdl_format)
        except Exception as exc:
            logger.exception("audio launch worker crashed")
            message = exc.message if isinstance(exc, SourceError) else text("audio_controller.start_failed", error=exc)
            self._launch_failed(session, message)

    def _launch(self, entry: Entry, session: int, ytdl_format: str) -> None:
        if self._stale(session):
            self._clear_pending(session)
            return
        vid = entry.get("id", "")
        local = entry.get("_local_path")
        if is_local_id(vid) and not local:  # mpv's yt-dlp hook would look the id up on YouTube
            self._launch_failed(session, text("local_files.missing"))
            return
        if vid:
            self._app.cache.suppress_video(vid)

        sponsorblock = self._start_sponsorblock(vid, session)
        stream_url = local or None  # a file on disk is played directly; ytdl options mean nothing to it
        if vid and not local:
            stream_url = self._resolve_stream(vid, session, ytdl_format or _DEFAULT_AUDIO_FORMAT)
            if self._stale(session):
                self._clear_pending(session)
                return
        if sponsorblock:
            sponsorblock.join(timeout=2.0)

        exe = player.mpv_exe(headless=True)
        if not exe:
            hint = text("audio_controller.windows_mpv_hint") if IS_WINDOWS else install_hint("mpv")
            self._launch_failed(session, text("audio_controller.no_mpv", hint=hint))
            return

        input_conf = player.write_input_conf()
        try:
            self._play_with_retries(entry, session, exe, input_conf, stream_url, ytdl_format)
        finally:
            try:
                os.unlink(input_conf)
            except OSError:
                pass

    def _resolve_stream(self, vid: str, session: int, fmt: str) -> str | None:
        urls, _ = streams.resolve_for_playback(
            vid,
            self._app.config,
            fmt,
            cancelled=lambda: self._stale(session),
            on_resolving=lambda: self._app.call_from_thread(
                self._app.notify, text("audio_controller.resolving"), timeout=5
            ),
        )
        return urls[0] if urls else None

    def _launch_failed(self, session: int, message: str) -> None:
        self._clear_pending(session)
        self._app.call_from_thread(self.log, f"[red]Error: {escape_markup(message)}[/red]")
        self._app.call_from_thread(self._app.notify, escape_markup(message), severity="error")
        self._app.call_from_thread(self._stop_if_current, session)

    def _play_with_retries(
        self,
        entry: Entry,
        session: int,
        exe: str,
        input_conf: str,
        stream_url: str | None,
        ytdl_format: str,
    ) -> None:
        config = self._app.config
        start = start_offset(entry, config)
        if start:
            resuming = text("audio_controller.resuming", clock=fmt_clock(start))
            self._app.call_from_thread(self._app.notify, resuming, timeout=3)
        command = _AudioCommand(
            config, entry, exe, input_conf, _socket_for(session), ytdl_format, stream_url, start
        )
        outcome = player.run_mpv_with_retries(
            command,
            headless=True,
            is_stale=lambda: self._stale(session),
            on_spawn=partial(self._adopt_process, session),
            on_retry=self._log_retry,
            capture_stderr=True,
        )
        self._handle_outcome(outcome, entry, session)

    def _adopt_process(self, session: int, proc: subprocess.Popen, _attempt: int) -> None:
        self._proc = proc
        self._clear_pending(session)

    def _log_retry(self, attempt: int) -> None:
        self._app.call_from_thread(self.log, f"[dim]Retrying audio ({attempt}/{player.MPV_MAX_ATTEMPTS})…[/dim]")

    def _handle_outcome(self, outcome: player.MpvOutcome, entry: Entry, session: int) -> None:
        if outcome.status == "stale":
            self._clear_pending(session)
            logger.debug("audio mpv stale session: %s", outcome.stderr)
        elif outcome.status == "launch_error":
            self._launch_failed(session, outcome.message)
        elif outcome.status == "ok":
            self._app.call_from_thread(self._on_finished, entry, session)
        elif outcome.status == "failed":
            self._app.call_from_thread(self._on_failed, entry, outcome.returncode, outcome.stderr, session)
