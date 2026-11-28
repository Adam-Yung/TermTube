"""The app-wide audio player: one headless mpv, its queue, polling and SponsorBlock skipping."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

from textual.message import Message
from textual.timer import Timer

from src import history, player
from src.entries import Entry
from src.plat import ProcessRegistry, cleanup_ipc, terminate_process
from src.progress import ProgressTracker
from src.sponsorblock import Segment, fetch_segments_async
from src.strings import text
from src.tui.audio_launch import AudioLaunchMixin, _socket_for
from src.tui.audio_queue import AudioQueueMixin
from src.tui.fmt import escape_markup
from src.tui.messages import AudioSegmentsLoaded, AudioTrackChanged, PlayerStateUpdated
from src.tui.segment_skip import SegmentSkipper

_POLL_INTERVAL_S = 0.5


def _no_log(_markup: str) -> None:
    """Default and detached debug-log sink."""


class AudioController(AudioQueueMixin, AudioLaunchMixin):
    """Background audio in a headless mpv, controlled over its IPC socket. One per app (``app.audio``).

    ``_session`` grows on every start. Each worker and callback carries the number it started
    under and does nothing once it no longer matches. Screens learn about changes through
    messages (``src/tui/messages.py``) broadcast to every screen on the stack; ``log`` is set by
    the screen that owns the debug log.
    """

    def __init__(self, app) -> None:
        self._app = app
        self.log: Callable[[str], None] = _no_log
        self._proc: subprocess.Popen | None = None
        self._entry: Entry | None = None
        self._queue: list[Entry] = []
        self._played: list[Entry] = []
        self._intent = 0
        self._session = 0
        self._stopped = False
        self._play_pending = False
        self._poll_timer: Timer | None = None
        self._poll_busy = False
        self._history_session = 0
        self._tracker: ProgressTracker | None = None
        self._skipper = SegmentSkipper()
        self._progress: tuple[float, float, bool] | None = None

    @property
    def is_playing(self) -> bool:
        return self._play_pending or (self._proc is not None and self._proc.poll() is None)

    @property
    def entry(self) -> Entry | None:
        return self._entry

    @property
    def intent(self) -> int:
        return self._intent

    def claim(self) -> int:
        """Number a request that loads before it plays; play, stop, back or a later claim makes it stale."""
        self._intent += 1
        return self._intent

    @property
    def segments(self) -> list[Segment]:
        return self._skipper.segments

    @property
    def progress(self) -> tuple[float, float, bool] | None:
        """Last ``(pos, dur, paused)`` read from mpv for the current track, or None before the first poll."""
        return self._progress

    def play_audio(self, entry: Entry, *, ytdl_format: str = "") -> None:
        """Play ``entry`` now, replacing the current track. The queue is kept."""
        self.claim()
        if self.is_playing:
            self._remember(self._entry, entry)
            self._stop(keep_player_mode=True)
        self._start(entry, ytdl_format=ytdl_format)

    def stop_audio(self) -> None:
        """Stop playback, drop the queue and forget the played tracks."""
        self.claim()
        self._queue.clear()
        self._played.clear()
        self._stop()

    def detach_log(self, sink: Callable[[str], None]) -> None:
        """Drop ``sink`` as the debug log when it is the current one (a screen leaving must not stay referenced)."""
        if self.log == sink:
            self.log = _no_log

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
        # A track is never both playing and queued: the queue page tells rows apart by id.
        self._queue = [e for e in self._queue if e.get("id") != entry.get("id")]
        self._stopped = False
        self._session += 1
        self._skipper = SegmentSkipper()
        self._progress = None
        self.log(f"[dim]Audio start: {escape_markup(entry.get('title', '')[:60])}[/dim]")
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
        self._skipper = SegmentSkipper()
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

    def _start_sponsorblock(self, vid: str, session: int):
        """Fetch the track's segments in the background; the thread to join, or None when there is nothing to ask."""
        config = self._app.config
        if not vid or not config.sponsorblock_enabled:
            return None
        return fetch_segments_async(
            vid,
            config.sponsorblock_categories,
            lambda segments: self._app.call_ui(self._apply_segments, session, segments),
        )

    def _apply_segments(self, session: int, segments: list[Segment]) -> None:
        if session == self._session:
            self._skipper = SegmentSkipper(segments)
            self._broadcast(lambda: AudioSegmentsLoaded(segments))

    def _on_finished(self, entry: Entry, session: int) -> None:
        if session != self._session:
            return
        title = entry.get("title", "")
        self.log(f"[dim]Audio finished: {escape_markup(title[:60])}[/dim]")
        self._finish_progress(completed=True)
        self._reset_playback()
        if self._queue:
            if title:
                self._app.notify(text("audio_controller.next_track", title=escape_markup(title[:40])), timeout=3)
            self._advance_queue(entry)
        else:
            self._played.clear()
            self._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))
            if title:
                self._app.notify(text("audio_controller.finished", title=escape_markup(title[:50])), timeout=4)

    def _on_failed(self, entry: Entry, returncode: int | None, stderr: str, session: int) -> None:
        if session != self._session:
            return
        title = entry.get("title", "") or entry.get("id", "")
        self._reset_playback()
        first_line = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        detail = player.friendly_mpv_error(first_line) if first_line else f"exit code {returncode}"
        self.log(f"[red]Audio failed: {escape_markup(title[:50])} — {escape_markup(detail)}[/red]")
        shown = text("audio_controller.failed", title=title[:40], detail=detail[:80])
        self._app.notify(escape_markup(shown), severity="error", timeout=8)
        if not self._advance_queue(entry):
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
        """Seek past the SponsorBlock segment containing ``pos``."""
        if not self._app.config.sponsorblock_auto_skip:
            return
        segment = self._skipper.take(pos)
        if segment is None:
            return
        player.send_ipc_command({"command": ["seek", segment.end, "absolute"]}, socket_path=_socket_for(session))
        self._app.call_from_thread(
            self._app.notify,
            text(
                "audio_controller.skipped_segment",
                category=segment.category,
                seconds=int(segment.end - segment.start),
            ),
            timeout=3,
        )
