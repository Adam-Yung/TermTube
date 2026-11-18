from __future__ import annotations

import functools
import os
import subprocess
import threading
from collections.abc import Callable

from textual.message import Message
from textual.timer import Timer

from src import history, logger, player, streams
from src.entries import Entry
from src.plat import (
    IS_WINDOWS,
    ProcessRegistry,
    cleanup_ipc,
    get_audio_ipc_path,
    install_hint,
    terminate_process,
)
from src.progress import ProgressTracker, start_offset
from src.sponsorblock import Segment, fetch_segments_async
from src.tui.fmt import fmt_clock
from src.tui.messages import AudioQueueChanged, AudioSegmentsLoaded, AudioTrackChanged, PlayerStateUpdated
from src.tui.screens.mixins.item_actions import watch_url

_POLL_INTERVAL_S = 0.5
_DEFAULT_AUDIO_FORMAT = "ba/b"


@functools.cache
def _socket_base() -> str:
    return get_audio_ipc_path()


def _mpv_log_path() -> str | None:
    """Beside the app's --debug log, so a failed mpv can explain itself. None unless --debug is on."""
    log = logger.log_file() if logger.is_debug() else None
    return str(log.with_name(f"{log.stem}-mpv.log")) if log else None


def _socket_for(session: int) -> str:
    """IPC path unique to ``session``, so a dying mpv never answers for the next one."""
    base = _socket_base()
    if session <= 1:
        return base
    stem, ext = os.path.splitext(base)
    return f"{stem}-{session}{ext}"


class AudioController:
    """Background audio in a headless mpv, controlled over its IPC socket. One per app (``app.audio``).

    ``_session`` grows on every start. Each worker and callback carries the number it started
    under and does nothing once it no longer matches. Screens learn about changes through
    messages (``src/tui/messages.py``) broadcast to every screen on the stack; ``log`` is set by
    the screen that owns the debug log.
    """

    def __init__(self, app) -> None:
        self._app = app
        self.log: Callable[[str], None] = lambda _markup: None
        self._proc: subprocess.Popen | None = None
        self._entry: Entry | None = None
        self._queue: list[Entry] = []
        self._session = 0
        self._stopped = False
        self._play_pending = False
        self._poll_timer: Timer | None = None
        self._poll_busy = False
        self._history_session = 0
        self._tracker: ProgressTracker | None = None
        self._segments: list[Segment] = []
        self._segment_idx = 0
        self._progress: tuple[float, float, bool] | None = None

    @property
    def is_playing(self) -> bool:
        return self._play_pending or (self._proc is not None and self._proc.poll() is None)

    @property
    def entry(self) -> Entry | None:
        return self._entry

    @property
    def queue(self) -> tuple[Entry, ...]:
        return tuple(self._queue)

    @property
    def segments(self) -> list[Segment]:
        return self._segments

    @property
    def progress(self) -> tuple[float, float, bool] | None:
        """Last ``(pos, dur, paused)`` read from mpv for the current track, or None before the first poll."""
        return self._progress

    def can_enqueue(self, entry: Entry) -> bool:
        """True while audio plays and ``entry`` is neither the current track nor already queued."""
        entry_id = entry.get("id")
        return (
            self.is_playing
            and entry_id != (self._entry or {}).get("id")
            and all(e.get("id") != entry_id for e in self._queue)
        )

    def play_audio(self, entry: Entry, *, ytdl_format: str = "") -> None:
        """Play ``entry`` now, replacing the current track. The queue is kept."""
        if self.is_playing:
            self._stop(keep_player_mode=True)
        self._start(entry, ytdl_format=ytdl_format)

    def enqueue_audio(self, entry: Entry) -> None:
        if not self.is_playing:
            self.play_audio(entry)
            return
        entry_id = entry.get("id")
        if entry_id and entry_id == (self._entry or {}).get("id"):
            self._app.notify("Already playing this track", timeout=2)
        elif entry_id and any(e.get("id") == entry_id for e in self._queue):
            self._app.notify("Already in queue", timeout=2)
        else:
            self._queue.append(entry)
            self._app.notify(f"Added to queue: {entry.get('title', 'video')[:40]}", timeout=3)
            self._queue_changed()

    def play_many(self, entries: list[Entry]) -> None:
        """Play the first entry now and queue the rest, replacing the queue (a playlist's play-all)."""
        if not entries:
            return
        self._queue = list(entries[1:])
        self.play_audio(entries[0])
        self._queue_changed()

    def enqueue_many(self, entries: list[Entry]) -> int:
        """Queue each entry not playing or queued, with one notice (idle: start the first). Returns the count."""
        fresh, seen = [], {(self._entry or {}).get("id"), *(e.get("id") for e in self._queue)}
        for entry in entries:
            if entry.get("id") not in seen:
                seen.add(entry.get("id"))
                fresh.append(entry)
        if not fresh:
            return 0
        if not self.is_playing:
            self.play_many(fresh)
        else:
            self._queue.extend(fresh)
            self._queue_changed()
        self._app.notify(f"Queued {len(fresh)} track{'s' if len(fresh) != 1 else ''}", timeout=3)
        return len(fresh)

    def skip_audio(self) -> None:
        if not self.is_playing or not self._queue:
            return
        self.play_audio(self._queue.pop(0))

    def stop_audio(self) -> None:
        """Stop playback and drop the queue."""
        self._queue.clear()
        self._stop()

    def move_queued(self, index: int, step: int) -> int:
        """Move the upcoming track at ``index`` by ``step`` places (clamped to the queue). Returns its new index."""
        if not 0 <= index < len(self._queue):
            return index
        new = min(len(self._queue) - 1, max(0, index + step))
        if new != index:
            self._queue.insert(new, self._queue.pop(index))
            self._queue_changed()
        return new

    def remove_queued(self, index: int) -> Entry | None:
        """Drop the upcoming track at ``index`` and return it (None when out of range); the playing one is not queued"""
        if not 0 <= index < len(self._queue):
            return None
        entry = self._queue.pop(index)
        self._queue_changed()
        return entry

    def insert_queued(self, index: int, entry: Entry) -> None:
        """Put ``entry`` back at ``index`` (undo of a removal), unless it is playing or queued again meanwhile."""
        if entry.get("id") == (self._entry or {}).get("id") or any(e.get("id") == entry.get("id") for e in self._queue):
            return
        self._queue.insert(min(max(index, 0), len(self._queue)), entry)
        self._queue_changed()

    def play_queued(self, index: int) -> None:
        """Play the upcoming track at ``index`` now. The tracks before it stay queued, in order (nothing is dropped)."""
        if not 0 <= index < len(self._queue):
            return
        entry = self._queue.pop(index)
        self.play_audio(entry)
        self._queue_changed()

    def _queue_changed(self) -> None:
        self._broadcast(lambda: AudioQueueChanged(len(self._queue)))

    def toggle_audio_pause(self) -> None:
        self._ipc({"command": ["cycle", "pause"]})

    def seek_audio(self, seconds: float) -> None:
        self._ipc({"command": ["seek", seconds, "relative"]})

    def seek_audio_percent(self, percent: float) -> None:
        self._ipc({"command": ["seek", percent, "absolute-percent"]})

    def _broadcast(self, make_message: Callable[[], Message]) -> None:
        """Post a fresh message to every screen on the stack, so a covered screen's bar stays current."""
        for screen in list(self._app.screen_stack):
            screen.post_message(make_message())

    def _ipc(self, cmd: dict) -> None:
        if self.is_playing:
            player.send_ipc_command(cmd, socket_path=_socket_for(self._session))

    def _stale(self, session: int) -> bool:
        return self._stopped or session != self._session

    def _clear_pending(self, session: int) -> None:
        if session == self._session:
            self._play_pending = False

    def _finish_progress(self, *, completed: bool = False) -> None:
        if self._tracker:
            self._tracker.finish(completed=completed)
            self._tracker = None

    def _reset_playback(self) -> None:
        self._finish_progress()
        self._proc = None
        self._entry = None
        self._progress = None
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _start(self, entry: Entry, *, ytdl_format: str = "") -> None:
        self._play_pending = True
        self._entry = entry
        self._stopped = False
        self._session += 1
        self._segments = []
        self._segment_idx = 0
        self._progress = None
        self.log(f"[dim]Audio start: {entry.get('title', '')[:60]}[/dim]")
        queue_len = len(self._queue)
        self._broadcast(lambda: AudioTrackChanged(entry, queue_len))
        threading.Thread(
            target=self._launch_worker, args=(entry, self._session, ytdl_format), daemon=True, name="audio-launch"
        ).start()
        self._poll_timer = self._app.set_interval(_POLL_INTERVAL_S, self._poll_tick)

    def _stop(self, *, keep_player_mode: bool = False) -> None:
        """Stop mpv and clean up its socket. Runs before the session counter moves, so it addresses the right socket."""
        self.log("[dim]Audio stop[/dim]")
        self._stopped = True
        self._play_pending = False
        self._segments = []
        self._segment_idx = 0
        socket_path = _socket_for(self._session)
        proc = self._proc
        if proc:
            if proc.poll() is None:
                player.send_ipc_command({"command": ["quit"]}, socket_path=socket_path)
                terminate_process(proc, timeout=2.0)
            ProcessRegistry.get().unregister(proc)
        self._reset_playback()
        if not keep_player_mode:
            self._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))
        player.close_persistent_socket(socket_path)
        cleanup_ipc(socket_path)

    def _stop_if_current(self, session: int) -> None:
        if session == self._session:
            self._stop()

    def _launch_worker(self, entry: Entry, session: int, ytdl_format: str) -> None:
        """Thread body. An exception here would otherwise vanish and leave the bar on "Buffering…" forever."""
        logger.debug("audio launch worker started (session %d)", session)
        try:
            self._launch(entry, session, ytdl_format)
        except Exception as exc:
            logger.exception("audio launch worker crashed")
            self._launch_failed(session, f"Audio failed to start: {exc}")

    def _launch(self, entry: Entry, session: int, ytdl_format: str) -> None:
        if self._stale(session):
            self._clear_pending(session)
            return
        config = self._app.config
        vid = entry.get("id", "")
        local = entry.get("_local_path")
        if vid:
            self._app.cache.suppress_video(vid)

        sponsorblock = self._start_sponsorblock(vid, session)
        fmt = ytdl_format or _DEFAULT_AUDIO_FORMAT
        stream_url = None
        if vid and not local:
            urls, _ = streams.resolve_for_playback(
                vid,
                config,
                fmt,
                cancelled=lambda: self._stale(session),
                on_resolving=lambda: self._app.call_from_thread(self._app.notify, "Resolving stream…", timeout=5),
            )
            if self._stale(session):
                self._clear_pending(session)
                return
            stream_url = urls[0] if urls else None
        elif local:
            stream_url = local  # a file on disk is played directly; ytdl options mean nothing to it
        if sponsorblock:
            sponsorblock.join(timeout=2.0)

        exe = player.mpv_exe(headless=True)
        if not exe:
            hint = (
                "run 'termtube --update' to install a standalone headless mpv.exe. "
                "mpv.net opens a GUI window and cannot be used for background audio."
                if IS_WINDOWS
                else install_hint("mpv")
            )
            self._launch_failed(session, f"No headless mpv found — {hint}")
            return

        input_conf = player.write_input_conf()
        try:
            self._play_with_retries(entry, session, exe, input_conf, stream_url, ytdl_format)
        finally:
            try:
                os.unlink(input_conf)
            except OSError:
                pass

    def _start_sponsorblock(self, vid: str, session: int):
        config = self._app.config
        if not vid or not config.sponsorblock_enabled:
            return None

        def apply(segments: list[Segment]) -> None:
            if session == self._session:
                self._segments = segments
                self._segment_idx = 0
                self._broadcast(lambda: AudioSegmentsLoaded(segments))

        return fetch_segments_async(
            vid,
            config.sponsorblock_categories,
            lambda segments: self._app.call_from_thread(apply, segments),
        )

    def _launch_failed(self, session: int, message: str) -> None:
        self._clear_pending(session)
        self._app.call_from_thread(self.log, f"[red]Error: {message}[/red]")
        self._app.call_from_thread(self._app.notify, message, severity="error")
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
        vid = entry.get("id", "")
        local = entry.get("_local_path")
        fmt = ytdl_format or _DEFAULT_AUDIO_FORMAT
        cookie_args = config.browser_cookie_args()
        url = stream_url
        start = start_offset(entry, config)
        if start:
            self._app.call_from_thread(self._app.notify, f"Resuming at {fmt_clock(start)}", timeout=3)

        def build_cmd(attempt: int) -> list[str]:
            nonlocal url
            if attempt > 1 and vid and not local:
                fresh = streams.re_resolve(vid, config, fmt)
                if fresh:
                    url = fresh[0]
            cmd = player.audio_command(
                exe,
                input_conf=input_conf,
                socket_path=_socket_for(session),
                title=entry.get("title", ""),
                stream_url=url,
                page_url=local or watch_url(vid),
                ytdl_format=ytdl_format,
                cookie_args=cookie_args,
                mpv_log=_mpv_log_path(),
                start=start,
            )
            logger.debug("audio mpv cmd: %s", " ".join(cmd))
            return cmd

        def on_spawn(proc: subprocess.Popen, _attempt: int) -> None:
            self._proc = proc
            self._clear_pending(session)

        outcome = player.run_mpv_with_retries(
            build_cmd,
            headless=True,
            is_stale=lambda: self._stale(session),
            on_spawn=on_spawn,
            on_retry=lambda attempt: self._app.call_from_thread(
                self.log, f"[dim]Retrying audio ({attempt}/{player.MPV_MAX_ATTEMPTS})…[/dim]"
            ),
            capture_stderr=True,
        )
        if outcome.status == "stale":
            self._clear_pending(session)
            logger.debug("audio mpv stale session: %s", outcome.stderr)
        elif outcome.status == "launch_error":
            self._launch_failed(session, outcome.message)
        elif outcome.status == "ok":
            self._app.call_from_thread(self._on_finished, entry, session)
        elif outcome.status == "failed":
            self._app.call_from_thread(self._on_failed, entry, outcome.returncode, outcome.stderr, session)

    def _advance_queue(self) -> bool:
        if not self._queue:
            return False
        self._start(self._queue.pop(0))
        return True

    def _on_finished(self, entry: Entry, session: int) -> None:
        if session != self._session:
            return
        title = entry.get("title", "")
        self.log(f"[dim]Audio finished: {title[:60]}[/dim]")
        self._finish_progress(completed=True)
        self._reset_playback()
        if self._queue:
            if title:
                self._app.notify(f"✓ {title[:40]}", timeout=3)
            self._advance_queue()
        else:
            self._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))
            if title:
                self._app.notify(f"✓ Finished: {title[:50]}", timeout=4)

    def _on_failed(self, entry: Entry, returncode: int | None, stderr: str, session: int) -> None:
        if session != self._session:
            return
        title = entry.get("title", "") or entry.get("id", "")
        self._reset_playback()
        first_line = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        detail = player.friendly_mpv_error(first_line) if first_line else f"exit code {returncode}"
        self.log(f"[red]Audio failed: {title[:50]} — {detail}[/red]")
        self._app.notify(f"✗ Audio failed: {title[:40]} ({detail[:80]})", severity="error", timeout=8)
        if not self._advance_queue():
            self._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))

    def _poll_tick(self) -> None:
        """Timer callback: start a poll unless the previous one is still waiting on mpv."""
        if self.is_playing and not self._poll_busy:
            self._poll_busy = True
            threading.Thread(target=self._poll_worker, args=(self._session,), daemon=True, name="audio-poll").start()

    def _poll_worker(self, session: int) -> None:
        try:
            self.poll_once(session)
        finally:
            self._poll_busy = False

    def poll_once(self, session: int) -> None:
        """Read mpv's position, apply SponsorBlock skipping and publish progress. Runs off the UI thread."""
        pos, dur, paused = player.poll_audio_properties(socket_path=_socket_for(session))
        if pos is None or dur is None or session != self._session:
            return
        self._app.call_from_thread(self._publish_progress, session, pos, dur, paused)
        self._skip_sponsor_segment(pos, session)

    def _publish_progress(self, session: int, pos: float, dur: float, paused: bool) -> None:
        if session != self._session:
            return
        if self._entry and self._history_session != session:
            self._history_session = session
            history.add(self._entry, self._app.config)
            self._tracker = ProgressTracker(self._entry)
        self._progress = (pos, dur, paused)
        if self._tracker:
            self._tracker.tick(pos, dur)
        self._broadcast(lambda: PlayerStateUpdated(pos, dur, paused, playing=True))

    def _skip_sponsor_segment(self, pos: float, session: int) -> None:
        """Seek past the SponsorBlock segment containing ``pos``. Segments are sorted by start."""
        if not self._app.config.sponsorblock_auto_skip:
            return
        segments = self._segments
        while self._segment_idx < len(segments) and segments[self._segment_idx].end <= pos:
            self._segment_idx += 1
        if self._segment_idx >= len(segments):
            return
        seg = segments[self._segment_idx]
        if seg.start <= pos < seg.end:
            self._segment_idx += 1
            player.send_ipc_command({"command": ["seek", seg.end, "absolute"]}, socket_path=_socket_for(session))
            self._app.call_from_thread(
                self._app.notify, f"Skipped: {seg.category} ({int(seg.end - seg.start)}s)", timeout=3
            )
