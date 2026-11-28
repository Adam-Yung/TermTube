from __future__ import annotations

import itertools
import os
import subprocess
import time
from functools import partial

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src import history
from src import player as player_mod
from src.entries import Entry
from src.local_files import is_local_id
from src.plat import (
    ProcessRegistry,
    cleanup_ipc,
    get_video_ipc_path,
    install_hint,
    terminate_process,
)
from src.progress import ProgressTracker, start_offset
from src.sponsorblock import Segment, fetch_segments_async
from src.strings import text
from src.tui.fmt import escape_markup, fmt_clock
from src.tui.screens.watch_command import VideoCommand, build_command
from src.tui.segment_skip import SegmentSkipper
from src.tui.urls import watch_url
from src.tui.widgets.segment_bar import EMPTY_COLOR, SegmentBar

_DEFAULT_FORMAT = "bv+ba/b"
_run_sockets = itertools.count(1)


def _run_socket() -> str:
    """A path per run item: the item left behind removes its socket while the next mpv may be creating one."""
    stem, ext = os.path.splitext(get_video_ipc_path())
    return f"{stem}-{next(_run_sockets)}{ext}"


_RUN_RESULTS = {0: "ended", player_mod.EXIT_NEXT: "next", player_mod.EXIT_PREV: "prev"}
_PROGRESS_COLOR = "#6666ff"


class WatchModal(ModalScreen[str]):
    """Launches mpv with a video window, shows progress in the TUI, and seeks/pauses/stops over IPC.

    Dismisses with ``ended``, ``next``, ``prev``, ``failed`` or ``stopped``. ``position`` (number, total) marks one item
    of a playlist run.
    """

    BINDINGS = [
        Binding("space", "pause_toggle", "Pause/Resume", show=True),
        Binding("h,left,left_square_bracket", "seek(-5)", "−5s", show=True),
        Binding("l,right,right_square_bracket", "seek(5)", "+5s", show=True),
        Binding("H,left_curly_bracket", "seek(-10)", "−10s", show=False),
        Binding("L,right_curly_bracket", "seek(10)", "+10s", show=False),
        *[Binding(str(n), f"seek_pct({n * 10})", f"{n * 10}%", show=False) for n in range(10)],
        Binding("greater_than_sign", "step('next')", "Next", show=False),
        Binding("less_than_sign", "step('prev')", "Previous", show=False),
        Binding("q,escape", "stop", "Stop", show=True),
    ]

    def __init__(self, entry: Entry, *, ytdl_format: str = "", position: tuple[int, int] | None = None) -> None:
        super().__init__()
        self._position = position
        self._entry = entry
        self._ytdl_format = ytdl_format
        self._proc: subprocess.Popen[bytes] | None = None
        self._stopped = False
        self._buffering_since: float = 0.0
        self._skipper = SegmentSkipper()
        self._bar = SegmentBar()
        self._dur: float = 0.0
        self._poll_timer = None
        self._socket = _run_socket() if position else get_video_ipc_path()
        self._tracker: ProgressTracker | None = None

    def compose(self) -> ComposeResult:
        title = self._entry.get("title") or text("watch_modal.unknown_title")
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="watch-dialog", classes="dialog"):
            header = text("watch_modal.header")
            if self._position:
                header = f"{header}  ·  {self._position[0]} / {self._position[1]}"
            yield Static(header, id="np-header")
            yield Static(f"[bold white]{escape_markup(title)}[/bold white]", id="np-title", markup=True)
            if channel:
                yield Static(escape_markup(channel), id="np-channel", markup=True)
            yield Static("", id="np-progress", markup=True)
            yield Static(text("watch_modal.loading"), id="np-time")
            yield Static(
                text("watch_modal.hint_run" if self._position else "watch_modal.hint"),
                id="np-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._buffering_since = time.monotonic()
        self._launch_video()
        self._poll_timer = self.set_interval(0.5, self._poll_mpv)

    @work(thread=True, exclusive=True, group="video_player")
    def _launch_video(self) -> None:
        vid = self._entry.get("id", "")
        local_path = self._entry.get("_local_path")
        title = self._entry.get("title", "")
        config = getattr(self.app, "config", None)
        fmt = self._ytdl_format or _DEFAULT_FORMAT
        if is_local_id(vid) and not local_path:  # mpv's yt-dlp hook would look the id up on YouTube
            self._fail_launch(text("local_files.missing"))
            return

        if vid and hasattr(self.app, "cache") and hasattr(self.app.cache, "suppress_video"):
            self.app.cache.suppress_video(vid)

        sb_thread = None
        if config and config.sponsorblock_enabled and vid:
            sb_thread = fetch_segments_async(
                vid, config.sponsorblock_categories, self._set_segments
            )

        urls: list[str] | None = [local_path] if local_path else None  # a local file is played directly, no ytdl
        if not local_path and vid and config:
            urls = self._resolve_urls(vid, config, fmt)
            if self._stopped:
                return

        if sb_thread:
            sb_thread.join(timeout=2.0)

        mpv_exe = player_mod.mpv_exe()
        if not mpv_exe:
            self._fail_launch(text("watch_modal.mpv_missing", hint=install_hint("mpv")))
            return

        input_conf = player_mod.write_input_conf(sequence=self._position is not None)
        page_url = local_path or watch_url(vid)
        cookie_args = config.browser_cookie_args() if config else []
        start = start_offset(self._entry, config) if config else None
        if start:
            self.app.call_from_thread(self.app.notify, text("watch_modal.resuming", time=fmt_clock(start)), timeout=3)

        build = partial(
            self._build_command, mpv_exe, input_conf, title,
            page_url=page_url, fmt=fmt, cookie_args=cookie_args, start=start,
        )
        refresh = None
        if not local_path and vid and config:
            refresh = partial(self._re_resolve, vid, config, fmt)
        outcome = player_mod.run_mpv_with_retries(
            VideoCommand(build, urls, refresh),
            headless=False,
            is_stale=lambda: self._stopped,
            on_spawn=self._on_spawn,
        )
        self._finish(outcome, input_conf, title)

    def _resolve_urls(self, vid: str, config, fmt: str) -> list[str] | None:
        from src import streams

        urls, _ = streams.resolve_for_playback(
            vid,
            config,
            fmt,
            cancelled=lambda: self._stopped,
            on_resolving=lambda: self.app.call_from_thread(
                self.app.notify, text("watch_modal.resolving"), timeout=5
            ),
        )
        return urls

    @staticmethod
    def _re_resolve(vid: str, config, fmt: str) -> list[str] | None:
        from src import streams

        return streams.re_resolve(vid, config, fmt)

    def _on_spawn(self, proc: subprocess.Popen[bytes], attempt: int) -> None:
        self._proc = proc
        if attempt == 1:
            history.add(self._entry, getattr(self.app, "config", None))
            self._tracker = ProgressTracker(self._entry)

    def _finish(self, outcome: player_mod.MpvOutcome, input_conf: str, title: str) -> None:
        """After mpv: save progress, clean up and dismiss with what happened."""
        clean_end = outcome.status == "ok" and outcome.returncode == 0
        if self._tracker:
            self._tracker.finish(completed=clean_end)
        self._cleanup_ipc(input_conf)
        if outcome.status == "launch_error":
            self._fail_launch(outcome.message)
        elif outcome.status == "failed":
            self.app.call_from_thread(
                self.app.notify,
                text("watch_modal.failed", code=outcome.returncode),
                severity="error",
                timeout=8,
            )
            self._dismiss_from_thread("failed")
        elif outcome.status != "stale":
            result = _RUN_RESULTS.get(outcome.returncode, "stopped") if outcome.status == "ok" else "stopped"
            self._dismiss_from_thread(result)
            if title and not self._position:
                try:
                    self.app.call_from_thread(
                        self.app.notify, text("watch_modal.finished", title=title[:50]), timeout=4
                    )
                except Exception:
                    pass

    def _set_segments(self, segments: list[Segment]) -> None:
        self._skipper = SegmentSkipper(segments)
        self._bar.set_segments(segments)

    def _build_command(
        self,
        exe: str,
        input_conf: str,
        title: str,
        urls: list[str] | None,
        page_url: str,
        fmt: str,
        cookie_args: list[str],
        start: float | None = None,
    ) -> list[str]:
        return build_command(
            exe, input_conf=input_conf, socket_path=self._socket, title=title, urls=urls,
            page_url=page_url, fmt=fmt, cookie_args=cookie_args, start=start,
        )

    def _fail_launch(self, message: str) -> None:
        self.app.call_from_thread(self.app.notify, message, severity="error")
        self.app.call_from_thread(self.dismiss, "stopped")

    def _dismiss_from_thread(self, result: str) -> None:
        try:
            self.app.call_from_thread(self.dismiss, result)
        except Exception:
            pass

    def _cleanup_ipc(self, input_conf: str) -> None:
        try:
            os.unlink(input_conf)
        except OSError:
            pass
        player_mod.close_persistent_socket(self._socket)
        cleanup_ipc(self._socket)

    def _poll_mpv(self) -> None:
        # mpv has exited: the launch worker reads the exit code and dismisses.
        if self._proc and self._proc.poll() is not None:
            return
        self._poll_mpv_threaded()

    @work(thread=True, exclusive=True, group="mpv_poll")
    def _poll_mpv_threaded(self) -> None:
        pos, dur, paused = player_mod.poll_audio_properties(socket_path=self._socket)
        if pos is not None and dur and float(dur) > 0:
            self._on_position(float(pos), float(dur), paused)
        elif self._buffering_since > 0:
            wait_s = int(time.monotonic() - self._buffering_since)
            buf_text = text("watch_modal.buffering_wait" if wait_s > 0 else "watch_modal.buffering", seconds=wait_s)
            self.app.call_from_thread(self._show_buffering, buf_text)

    def _on_position(self, pos: float, dur: float, paused: bool) -> None:
        """Poll thread: record progress, then either skip a sponsor segment or redraw."""
        self._dur = dur
        if self._tracker:
            self._tracker.tick(pos, dur)
        if not self._skip_sponsor_segment(pos):
            self.app.call_from_thread(self._show_position, pos, dur, paused)

    def _skip_sponsor_segment(self, pos: float) -> bool:
        config = getattr(self.app, "config", None)
        if not (config and config.sponsorblock_auto_skip):
            return False
        segment = self._skipper.take(pos)
        if segment is None:
            return False
        self._ipc(["seek", segment.end, "absolute"])
        self.app.call_from_thread(
            self.notify,
            text("watch_modal.skipped", category=segment.category, seconds=int(segment.end - segment.start)),
            timeout=3,
        )
        return True

    def _show_position(self, pos: float, dur: float, paused: bool) -> None:
        try:
            bar_width = max(8, (self.query_one("#watch-dialog").size.width or 60) - 6)
            self.query_one("#np-progress", Static).update(self._render_bar(pos, dur, bar_width))
            pause_indicator = text("watch_modal.paused") if paused else ""
            self.query_one("#np-time", Static).update(f"{fmt_clock(pos)}  /  {fmt_clock(dur)}{pause_indicator}")
        except Exception:
            pass

    def _show_buffering(self, message: str) -> None:
        try:
            self.query_one("#np-time", Static).update(message)
        except Exception:
            pass

    def _render_bar(self, pos: float, dur: float, width: int) -> str:
        width = max(4, width)
        if dur <= 0:
            return f"[{EMPTY_COLOR}]{'─' * width}[/{EMPTY_COLOR}]"
        return self._bar.render(pos, dur, width, _PROGRESS_COLOR)

    def _ipc(self, cmd: list) -> None:
        player_mod.send_ipc_command({"command": cmd}, socket_path=self._socket)

    def action_pause_toggle(self) -> None:
        self._ipc(["cycle", "pause"])

    def action_seek(self, seconds: int) -> None:
        self._ipc(["seek", seconds, "relative"])

    def action_seek_pct(self, pct: int) -> None:
        self._ipc(["seek", pct, "absolute-percent"])

    def action_step(self, result: str) -> None:
        if self._position is None:
            self.notify(text("watch_modal.not_a_playlist"), timeout=2)
            return
        self._end(result)

    def action_stop(self) -> None:
        self._end("stopped")

    def _end(self, result: str) -> None:
        """Quit mpv and dismiss with ``result``; the launch worker sees ``_stopped`` and stays out."""
        if self._stopped:
            return
        self._stopped = True
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        self._ipc(["quit"])
        terminate_process(self._proc, timeout=2.0)
        if self._proc:
            ProcessRegistry.get().unregister(self._proc)
        try:
            self.dismiss(result)
        except Exception:
            pass
