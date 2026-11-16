from __future__ import annotations

import functools
import os
import subprocess
import time

from textual import work
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
from src.tui.messages import PlayerStateUpdated
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


class AudioPlayerMixin:
    """Background audio in a headless mpv, controlled over its IPC socket.

    Needs from the host screen: ``_detail()`` (``DetailFocusMixin``), ``_selected_entry()``
    (``ListNavMixin``), ``_log()`` (``DebugLogMixin``), ``notify`` and ``set_interval``.
    Call ``_init_audio`` from ``__init__``.

    ``_audio_session`` grows on every start. Each worker and callback carries the number
    it started under and does nothing once it no longer matches.
    """

    def _init_audio(self) -> None:
        self._audio_proc: subprocess.Popen | None = None
        self._audio_entry: dict | None = None
        self._audio_queue: list[dict] = []
        self._audio_session = 0
        self._audio_stopped = False
        self._play_pending = False
        self._audio_poll_timer: Timer | None = None
        self._history_session = 0
        self._segments: list[Segment] = []
        self._segment_idx = 0

    @property
    def is_audio_playing(self) -> bool:
        return self._play_pending or (self._audio_proc is not None and self._audio_proc.poll() is None)

    @property
    def audio_entry(self) -> dict | None:
        return self._audio_entry

    @property
    def audio_queue_len(self) -> int:
        return len(self._audio_queue)

    def can_enqueue(self, entry: dict) -> bool:
        """True while audio plays and ``entry`` is neither the current track nor already queued."""
        entry_id = entry.get("id")
        return (
            self.is_audio_playing
            and entry_id != (self._audio_entry or {}).get("id")
            and all(e.get("id") != entry_id for e in self._audio_queue)
        )

    def play_audio(self, entry: dict, *, ytdl_format: str = "") -> None:
        """Play ``entry`` now, replacing the current track. The queue is kept."""
        if self.is_audio_playing:
            self._audio_session += 1
            self._stop_audio(keep_player_mode=True)
        self._start_audio(entry, ytdl_format=ytdl_format)

    def enqueue_audio(self, entry: dict) -> None:
        if not self.is_audio_playing:
            self.play_audio(entry)
            return
        entry_id = entry.get("id")
        if entry_id and entry_id == (self._audio_entry or {}).get("id"):
            self.notify("Already playing this track", timeout=2)
        elif entry_id and any(e.get("id") == entry_id for e in self._audio_queue):
            self.notify("Already in queue", timeout=2)
        else:
            self._audio_queue.append(entry)
            self.notify(f"Added to queue: {entry.get('title', 'video')[:40]}", timeout=3)
            self._refresh_queue_hint()

    def skip_audio(self) -> None:
        if not self.is_audio_playing or not self._audio_queue:
            return
        self.play_audio(self._audio_queue.pop(0))

    def stop_audio(self) -> None:
        """Stop playback and drop the queue."""
        self._audio_queue.clear()
        self._stop_audio()

    def toggle_audio_pause(self) -> None:
        self._audio_ipc({"command": ["cycle", "pause"]})

    def seek_audio(self, seconds: float) -> None:
        self._audio_ipc({"command": ["seek", seconds, "relative"]})

    def seek_audio_percent(self, percent: float) -> None:
        self._audio_ipc({"command": ["seek", percent, "absolute-percent"]})

    def _audio_socket(self) -> str:
        """IPC path unique to this session, so a dying mpv never answers for the next one."""
        base = _socket_base()
        if self._audio_session <= 1:
            return base
        stem, ext = os.path.splitext(base)
        return f"{stem}-{self._audio_session}{ext}"

    def _audio_ipc(self, cmd: dict) -> None:
        if self.is_audio_playing:
            player.send_ipc_command(cmd, socket_path=self._audio_socket())

    def _stale(self, session: int) -> bool:
        return self._audio_stopped or session != self._audio_session

    def _clear_pending(self, session: int) -> None:
        if session == self._audio_session:
            self._play_pending = False

    def _reset_playback(self) -> None:
        self._audio_proc = None
        self._audio_entry = None
        if self._audio_poll_timer:
            self._audio_poll_timer.stop()
            self._audio_poll_timer = None

    def _refresh_queue_hint(self, focused_entry: dict | None = None) -> None:
        """Hide the enqueue hint when the focused row is already playing or queued."""
        try:
            bar = self._detail().action_bar
        except Exception:
            return
        entry = focused_entry or self._selected_entry()
        focused_id = entry.get("id") if entry else None
        playing_id = (self._audio_entry or {}).get("id")
        queued = {e.get("id") for e in self._audio_queue}
        bar.update_queue_hint(
            len(self._audio_queue),
            hide_e=bool(focused_id and (focused_id == playing_id or focused_id in queued)),
        )

    def _start_audio(self, entry: dict, *, ytdl_format: str = "") -> None:
        self._play_pending = True
        self._audio_entry = entry
        self._audio_stopped = False
        self._audio_session += 1
        self._segments = []
        self._segment_idx = 0
        self._log(f"[dim]Audio start: {entry.get('title', '')[:60]}[/dim]")
        self._detail().action_bar.set_player_mode(entry, queue_len=len(self._audio_queue))
        self._refresh_queue_hint()
        self._launch_audio_worker(entry, self._audio_session, ytdl_format)
        self._audio_poll_timer = self.set_interval(_POLL_INTERVAL_S, self._poll_audio_ipc)

    def _stop_audio(self, *, keep_player_mode: bool = False) -> None:
        self._log("[dim]Audio stop[/dim]")
        self._audio_stopped = True
        self._play_pending = False
        self._segments = []
        self._segment_idx = 0
        socket_path = self._audio_socket()
        proc = self._audio_proc
        if proc:
            if proc.poll() is None:
                player.send_ipc_command({"command": ["quit"]}, socket_path=socket_path)
                terminate_process(proc, timeout=2.0)
            ProcessRegistry.get().unregister(proc)
        self._reset_playback()
        if not keep_player_mode:
            self._detail().action_bar.set_actions_mode()
        self.app.screen.post_message(PlayerStateUpdated(0.0, 0.0, False, playing=False))
        player.close_persistent_socket(socket_path)
        cleanup_ipc(socket_path)

    @work(thread=True, group="audio_player")
    def _launch_audio_worker(self, entry: dict, session: int, ytdl_format: str) -> None:
        if self._stale(session):
            self._clear_pending(session)
            return
        config = self.app.config
        vid = entry.get("id", "")
        local = entry.get("_local_path")
        if vid:
            self.app.cache.suppress_video(vid)

        sponsorblock = self._start_sponsorblock(vid, session)
        fmt = ytdl_format or _DEFAULT_AUDIO_FORMAT
        stream_url = None
        if vid and not local:
            urls, _ = streams.resolve_for_playback(
                vid,
                config,
                fmt,
                cancelled=lambda: self._stale(session),
                on_resolving=lambda: self.app.call_from_thread(
                    self.notify, "Resolving stream…", timeout=5
                ),
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
        config = self.app.config
        if not vid or not config.sponsorblock_enabled:
            return None

        def apply(segments: list[Segment]) -> None:
            if session == self._audio_session:
                self._segments = segments
                self._segment_idx = 0
                self._detail().action_bar.set_segments(segments)

        return fetch_segments_async(
            vid,
            config.sponsorblock_categories,
            lambda segments: self.app.call_from_thread(apply, segments),
        )

    def _launch_failed(self, session: int, message: str) -> None:
        self._clear_pending(session)
        self.app.call_from_thread(self._log, f"[red]Error: {message}[/red]")
        self.app.call_from_thread(self.notify, message, severity="error")
        self.app.call_from_thread(self._stop_audio)

    def _play_with_retries(
        self,
        entry: dict,
        session: int,
        exe: str,
        input_conf: str,
        stream_url: str | None,
        ytdl_format: str,
    ) -> None:
        config = self.app.config
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
                socket_path=self._audio_socket(),
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
                self.app.call_from_thread(self._on_audio_finished, entry, session)
                return
            if returncode == _EXIT_SIGNAL:
                return
            if attempt < _MAX_ATTEMPTS:
                logger.debug("audio retry %d/%d for %s (rc=%s)", attempt, _MAX_ATTEMPTS, vid, returncode)
                self.app.call_from_thread(
                    self._log, f"[dim]Retrying audio ({attempt}/{_MAX_ATTEMPTS})…[/dim]"
                )
                time.sleep(_RETRY_DELAY_S)
            else:
                logger.warning(
                    "audio mpv failed after %d attempts (rc=%s) for %s: %s",
                    _MAX_ATTEMPTS, returncode, vid, stderr or "(no stderr output)",
                )
                self.app.call_from_thread(
                    self._on_audio_failed, entry, returncode, stderr, session
                )

    def _run_mpv(self, cmd: list[str], session: int) -> tuple[int, str]:
        """Run mpv to completion. Blocks the worker thread; returns its exit code and stderr."""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            **get_popen_kwargs(headless=True),
        )
        self._audio_proc = proc
        self._clear_pending(session)
        ProcessRegistry.get().register(proc)
        try:
            _, stderr = proc.communicate()
        except Exception:
            stderr = ""
        return proc.returncode, (stderr or "").strip()

    def _advance_queue(self) -> bool:
        if not self._audio_queue:
            return False
        self._start_audio(self._audio_queue.pop(0))
        return True

    def _on_audio_finished(self, entry: dict, session: int) -> None:
        if session != self._audio_session:
            return
        title = entry.get("title", "")
        self._log(f"[dim]Audio finished: {title[:60]}[/dim]")
        self._reset_playback()
        if self._audio_queue:
            if title:
                self.notify(f"✓ {title[:40]}", timeout=3)
            self._advance_queue()
        else:
            self._detail().action_bar.set_actions_mode()
            if title:
                self.notify(f"✓ Finished: {title[:50]}", timeout=4)

    def _on_audio_failed(
        self, entry: dict, returncode: int | None, stderr: str, session: int
    ) -> None:
        if session != self._audio_session:
            return
        title = entry.get("title", "") or entry.get("id", "")
        self._reset_playback()
        first_line = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        detail = player.friendly_mpv_error(first_line) if first_line else f"exit code {returncode}"
        self._log(f"[red]Audio failed: {title[:50]} — {detail}[/red]")
        self.notify(f"✗ Audio failed: {title[:40]} ({detail[:80]})", severity="error", timeout=8)
        if not self._advance_queue():
            self._detail().action_bar.set_actions_mode()

    def _poll_audio_ipc(self) -> None:
        if self.is_audio_playing:
            self._poll_audio_worker(self._audio_session)

    @work(thread=True, exclusive=True, group="audio_poll")
    def _poll_audio_worker(self, session: int) -> None:
        pos, dur, paused = player.poll_audio_properties(socket_path=self._audio_socket())
        if pos is None or dur is None or session != self._audio_session:
            return
        self.app.call_from_thread(
            self._publish_progress, session, pos, dur, paused
        )
        self._skip_sponsor_segment(pos)

    def _publish_progress(self, session: int, pos: float, dur: float, paused: bool) -> None:
        if session != self._audio_session:
            return
        if self._audio_entry and self._history_session != session:
            self._history_session = session
            history.add(self._audio_entry)
        self._detail().action_bar.update_progress(pos, dur, paused)
        self.app.screen.post_message(PlayerStateUpdated(pos, dur, paused, playing=True))

    def _skip_sponsor_segment(self, pos: float) -> None:
        """Seek past the SponsorBlock segment containing ``pos``. Segments are sorted by start."""
        if not self.app.config.sponsorblock_auto_skip:
            return
        segments = self._segments
        while self._segment_idx < len(segments) and segments[self._segment_idx].end <= pos:
            self._segment_idx += 1
        if self._segment_idx >= len(segments):
            return
        seg = segments[self._segment_idx]
        if seg.start <= pos < seg.end:
            self._segment_idx += 1
            player.send_ipc_command(
                {"command": ["seek", seg.end, "absolute"]}, socket_path=self._audio_socket()
            )
            self.app.call_from_thread(
                self.notify, f"Skipped: {seg.category} ({int(seg.end - seg.start)}s)", timeout=3
            )
