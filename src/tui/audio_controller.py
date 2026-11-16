from __future__ import annotations

import functools
import os
import subprocess
import threading
import time
from collections.abc import Callable

from textual.message import Message
from textual.timer import Timer

from src import history, logger, player, streams
from src.plat import (
    IS_WINDOWS,
    ProcessRegistry,
    cleanup_ipc,
    get_audio_ipc_path,
    get_popen_kwargs,
    install_hint,
    terminate_process,
)
from src.sponsorblock import Segment, fetch_segments_async
from src.tui.messages import AudioQueueChanged, AudioSegmentsLoaded, AudioTrackChanged, PlayerStateUpdated
from src.tui.screens.mixins.item_actions import watch_url

_MAX_ATTEMPTS = 3
_RETRY_DELAY_S = 1.0
_POLL_INTERVAL_S = 0.5
_DEFAULT_AUDIO_FORMAT = "ba/b"
# mpv exit codes: 0 end of file, 3 killed by a signal, 4 quit by command.
_EXIT_EOF, _EXIT_SIGNAL, _EXIT_QUIT = 0, 3, 4


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
        self._entry: dict | None = None
        self._queue: list[dict] = []
        self._session = 0
        self._stopped = False
        self._play_pending = False
        self._poll_timer: Timer | None = None
        self._poll_busy = False
        self._history_session = 0
        self._segments: list[Segment] = []
        self._segment_idx = 0
        self._progress: tuple[float, float, bool] | None = None

    @property
    def is_playing(self) -> bool:
        return self._play_pending or (self._proc is not None and self._proc.poll() is None)

    @property
    def entry(self) -> dict | None:
        return self._entry

    @property
    def queue(self) -> tuple[dict, ...]:
        return tuple(self._queue)

    @property
    def segments(self) -> list[Segment]:
        return self._segments

    @property
    def progress(self) -> tuple[float, float, bool] | None:
        """Last ``(pos, dur, paused)`` read from mpv for the current track, or None before the first poll."""
        return self._progress

    def can_enqueue(self, entry: dict) -> bool:
        """True while audio plays and ``entry`` is neither the current track nor already queued."""
        entry_id = entry.get("id")
        return (
            self.is_playing
            and entry_id != (self._entry or {}).get("id")
            and all(e.get("id") != entry_id for e in self._queue)
        )

    def play_audio(self, entry: dict, *, ytdl_format: str = "") -> None:
        """Play ``entry`` now, replacing the current track. The queue is kept."""
        if self.is_playing:
            self._stop(keep_player_mode=True)
        self._start(entry, ytdl_format=ytdl_format)

    def enqueue_audio(self, entry: dict) -> None:
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
            self._broadcast(lambda: AudioQueueChanged(len(self._queue)))

    def skip_audio(self) -> None:
        if not self.is_playing or not self._queue:
            return
        self.play_audio(self._queue.pop(0))

    def stop_audio(self) -> None:
        """Stop playback and drop the queue."""
        self._queue.clear()
        self._stop()

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

    def _reset_playback(self) -> None:
        self._proc = None
        self._entry = None
        self._progress = None
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _start(self, entry: dict, *, ytdl_format: str = "") -> None:
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

    def _launch_worker(self, entry: dict, session: int, ytdl_format: str) -> None:
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
        entry: dict,
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

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if self._stale(session):
                self._clear_pending(session)
                return
            if attempt > 1 and vid and not local:
                urls = streams.re_resolve(vid, config, fmt)
                if urls:
                    stream_url = urls[0]
            cmd = player.audio_command(
                exe,
                input_conf=input_conf,
                socket_path=_socket_for(session),
                title=entry.get("title", ""),
                stream_url=stream_url,
                page_url=local or watch_url(vid),
                ytdl_format=ytdl_format,
                cookie_args=cookie_args,
            )
            logger.debug("audio mpv cmd: %s", " ".join(cmd))
            try:
                returncode, stderr = self._run_mpv(cmd, session)
            except FileNotFoundError:
                self._launch_failed(session, f"mpv not found — install with: {install_hint('mpv')}")
                return
            except OSError as exc:
                self._launch_failed(session, f"Failed to launch mpv: {exc}")
                return

            if self._stale(session):
                logger.debug("audio mpv stderr (stale session): %s", stderr)
                return
            if returncode in (_EXIT_EOF, _EXIT_QUIT):
                self._app.call_from_thread(self._on_finished, entry, session)
                return
            if returncode == _EXIT_SIGNAL:
                return
            if attempt < _MAX_ATTEMPTS:
                logger.debug("audio retry %d/%d for %s (rc=%s)", attempt, _MAX_ATTEMPTS, vid, returncode)
                self._app.call_from_thread(self.log, f"[dim]Retrying audio ({attempt}/{_MAX_ATTEMPTS})…[/dim]")
                time.sleep(_RETRY_DELAY_S)
            else:
                logger.warning(
                    "audio mpv failed after %d attempts (rc=%s) for %s: %s",
                    _MAX_ATTEMPTS, returncode, vid, stderr or "(no stderr output)",
                )
                self._app.call_from_thread(self._on_failed, entry, returncode, stderr, session)

    def _run_mpv(self, cmd: list[str], session: int) -> tuple[int, str]:
        """Run mpv to completion. Blocks the worker thread; returns its exit code and stderr."""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            **get_popen_kwargs(headless=True),
        )
        self._proc = proc
        self._clear_pending(session)
        ProcessRegistry.get().register(proc)
        try:
            _, stderr = proc.communicate()
        except Exception:
            stderr = ""
        return proc.returncode, (stderr or "").strip()

    def _advance_queue(self) -> bool:
        if not self._queue:
            return False
        self._start(self._queue.pop(0))
        return True

    def _on_finished(self, entry: dict, session: int) -> None:
        if session != self._session:
            return
        title = entry.get("title", "")
        self.log(f"[dim]Audio finished: {title[:60]}[/dim]")
        self._reset_playback()
        if self._queue:
            if title:
                self._app.notify(f"✓ {title[:40]}", timeout=3)
            self._advance_queue()
        else:
            self._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))
            if title:
                self._app.notify(f"✓ Finished: {title[:50]}", timeout=4)

    def _on_failed(self, entry: dict, returncode: int | None, stderr: str, session: int) -> None:
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
            history.add(self._entry)
        self._progress = (pos, dur, paused)
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
