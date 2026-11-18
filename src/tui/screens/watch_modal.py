from __future__ import annotations

import os
import subprocess
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src import history
from src import player as player_mod
from src.entries import Entry
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

_DEFAULT_FORMAT = "bv+ba/b"


class WatchModal(ModalScreen[bool]):
    """Launches mpv with a video window, shows progress in the TUI, and seeks/pauses/stops over IPC."""

    BINDINGS = [
        Binding("space", "pause_toggle", "Pause/Resume", show=True),
        Binding("h,left,left_square_bracket", "seek(-5)", "−5s", show=True),
        Binding("l,right,right_square_bracket", "seek(5)", "+5s", show=True),
        Binding("H,left_curly_bracket", "seek(-10)", "−10s", show=False),
        Binding("L,right_curly_bracket", "seek(10)", "+10s", show=False),
        *[Binding(str(n), f"seek_pct({n * 10})", f"{n * 10}%", show=False) for n in range(10)],
        Binding("q,escape", "stop", "Stop", show=True),
    ]

    def __init__(self, entry: Entry, *, ytdl_format: str = "") -> None:
        super().__init__()
        self._entry = entry
        self._ytdl_format = ytdl_format
        self._proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._stopped = False
        self._buffering_since: float = 0.0
        self._segments: list[Segment] = []
        self._sb_next_idx: int = 0  # sorted pointer for O(1) segment scan
        self._dur: float = 0.0
        self._poll_timer = None
        self._socket = get_video_ipc_path()
        self._tracker: ProgressTracker | None = None
        self._segment_cols: list[bool] = []
        self._segment_cols_width: int = 0
        self._segment_cols_dur: float = 0.0

    def compose(self) -> ComposeResult:
        title = self._entry.get("title") or text("watch_modal.unknown_title")
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="watch-dialog", classes="dialog"):
            yield Static(text("watch_modal.header"), id="np-header")
            yield Static(f"[bold white]{escape_markup(title)}[/bold white]", id="np-title", markup=True)
            if channel:
                yield Static(escape_markup(channel), id="np-channel", markup=True)
            yield Static("", id="np-progress", markup=True)
            yield Static(text("watch_modal.loading"), id="np-time")
            yield Static(
                text("watch_modal.hint"),
                id="np-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._buffering_since = time.monotonic()
        self._launch_video()
        self._poll_timer = self.set_interval(0.5, self._poll_mpv)

    @work(thread=True, exclusive=True, group="video_player")
    def _launch_video(self) -> None:
        from src import streams

        vid = self._entry.get("id", "")
        local_path = self._entry.get("_local_path")
        title = self._entry.get("title", "")
        config = getattr(self.app, "config", None)
        fmt = self._ytdl_format or _DEFAULT_FORMAT

        if vid and hasattr(self.app, "cache") and hasattr(self.app.cache, "suppress_video"):
            self.app.cache.suppress_video(vid)

        sb_thread = None
        if config and config.sponsorblock_enabled and vid:
            sb_thread = fetch_segments_async(
                vid, config.sponsorblock_categories, self._set_segments
            )

        urls: list[str] | None = [local_path] if local_path else None  # a local file is played directly, no ytdl
        if not local_path and vid and config:
            urls, _ = streams.resolve_for_playback(
                vid,
                config,
                fmt,
                cancelled=lambda: self._stopped,
                on_resolving=lambda: self.app.call_from_thread(
                    self.app.notify, text("watch_modal.resolving"), timeout=5
                ),
            )
            if self._stopped:
                return

        if sb_thread:
            sb_thread.join(timeout=2.0)

        mpv_exe = player_mod.mpv_exe()
        if not mpv_exe:
            self._fail_launch(text("watch_modal.mpv_missing", hint=install_hint("mpv")))
            return

        input_conf = player_mod.write_input_conf()
        page_url = local_path or f"https://www.youtube.com/watch?v={vid}"
        cookie_args = config.browser_cookie_args() if config else []
        start = start_offset(self._entry, config) if config else None
        if start:
            self.app.call_from_thread(self.app.notify, text("watch_modal.resuming", time=fmt_clock(start)), timeout=3)

        def build(stream_urls: list[str] | None) -> list[str]:
            return self._build_command(mpv_exe, input_conf, title, stream_urls, page_url, fmt, cookie_args, start)

        current = urls

        def build_cmd(attempt: int) -> list[str]:
            nonlocal current
            if attempt > 1 and not local_path and vid and config:
                current = streams.re_resolve(vid, config, fmt) or current
            return build(current)

        def on_spawn(proc: subprocess.Popen, attempt: int) -> None:
            self._proc = proc
            if attempt == 1:
                history.add(self._entry, getattr(self.app, "config", None))
                self._tracker = ProgressTracker(self._entry)

        outcome = player_mod.run_mpv_with_retries(
            build_cmd, headless=False, is_stale=lambda: self._stopped, on_spawn=on_spawn
        )
        if self._tracker:
            self._tracker.finish(completed=outcome.status == "ok" and outcome.returncode == 0)
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
            self._dismiss_from_thread(False)
        elif outcome.status != "stale":
            self._dismiss_from_thread(True)
            if title:
                try:
                    self.app.call_from_thread(
                        self.app.notify, text("watch_modal.finished", title=title[:50]), timeout=4
                    )
                except Exception:
                    pass

    def _set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self._sb_next_idx = 0
        self._segment_cols = []

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
        cmd = [
            exe,
            f"--input-conf={input_conf}",
            f"--input-ipc-server={self._socket}",
            "--no-terminal",
            "--really-quiet",
            "--msg-level=all=no",
            "--cache=yes",
            "--demuxer-max-bytes=150M",
            *player_mod.start_args(start),
        ]
        if title:
            cmd += [f"--title={title}", f"--force-media-title={title}"]
        if urls:
            cmd.append("--no-ytdl")
            if len(urls) == 2:
                cmd.append(f"--audio-file={urls[1]}")
            return cmd + ["--", urls[0]]
        cmd.append(f"--ytdl-format={fmt}")
        raw = player_mod.cookie_args_to_ytdl_raw(cookie_args)
        if raw:
            cmd.append(f"--ytdl-raw-options={raw}")
        return cmd + ["--", page_url]

    def _fail_launch(self, message: str) -> None:
        self.app.call_from_thread(self.app.notify, message, severity="error")
        self.app.call_from_thread(self.dismiss, False)

    def _dismiss_from_thread(self, result: bool) -> None:
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
        # The user closed the external mpv window.
        if self._proc and self._proc.poll() is not None:
            if not self._stopped:
                self._stopped = True
                try:
                    self.dismiss(True)
                except Exception:
                    pass
            return
        self._poll_mpv_threaded()

    @work(thread=True, exclusive=True, group="mpv_poll")
    def _poll_mpv_threaded(self) -> None:
        pos, dur, paused = player_mod.poll_audio_properties(socket_path=self._socket)
        if pos is not None and dur and float(dur) > 0:
            pos_f = float(pos)
            dur_f = float(dur)
            self._dur = dur_f
            if self._tracker:
                self._tracker.tick(pos_f, dur_f)
            # Segments are sorted by start; the pointer only moves forward.
            config = getattr(self.app, "config", None)
            if config and config.sponsorblock_auto_skip and self._segments:
                segs = self._segments
                while self._sb_next_idx < len(segs) and segs[self._sb_next_idx].end <= pos_f:
                    self._sb_next_idx += 1
                if self._sb_next_idx < len(segs):
                    seg = segs[self._sb_next_idx]
                    if seg.start <= pos_f < seg.end:
                        self._sb_next_idx += 1
                        skip_dur = int(seg.end - seg.start)
                        self._ipc(["seek", seg.end, "absolute"])
                        self.app.call_from_thread(
                            self.notify,
                            text("watch_modal.skipped", category=seg.category, seconds=skip_dur),
                            timeout=3,
                        )
                        return

            def _update_ui():
                try:
                    bar_width = max(8, (self.query_one("#watch-dialog").size.width or 60) - 6)
                    self.query_one("#np-progress", Static).update(
                        self._render_bar(pos_f, dur_f, bar_width)
                    )
                    pause_indicator = text("watch_modal.paused") if paused else ""
                    self.query_one("#np-time", Static).update(
                        f"{fmt_clock(pos_f)}  /  {fmt_clock(dur_f)}{pause_indicator}"
                    )
                except Exception:
                    pass

            self.app.call_from_thread(_update_ui)
        elif self._buffering_since > 0:
            wait_s = int(time.monotonic() - self._buffering_since)
            buf_text = text("watch_modal.buffering_wait" if wait_s > 0 else "watch_modal.buffering", seconds=wait_s)
            def _update_buf():
                try:
                    self.query_one("#np-time", Static).update(buf_text)
                except Exception:
                    pass
            self.app.call_from_thread(_update_buf)

    def _render_bar(self, pos: float, dur: float, width: int) -> str:
        width = max(4, width)
        if dur <= 0:
            return f"[#2a2a40]{'─' * width}[/#2a2a40]"
        frac = min(pos / dur, 1.0)
        filled = int(frac * width)
        progress_color = "#6666ff"
        sponsor_color = "#22c55e"
        sponsor_dim = "#166534"

        if not self._segments:
            empty = width - filled
            return (
                f"[{progress_color}]{'█' * filled}[/{progress_color}]"
                f"[#2a2a40]{'░' * empty}[/#2a2a40]"
            )

        if (
            self._segment_cols_width != width
            or self._segment_cols_dur != dur
            or len(self._segment_cols) != width
        ):
            cols: list[bool] = []
            for col in range(width):
                t = (col / width) * dur
                cols.append(any(s.start <= t < s.end for s in self._segments))
            self._segment_cols = cols
            self._segment_cols_width = width
            self._segment_cols_dur = dur

        parts: list[str] = []
        prev_color: str | None = None
        run: list[str] = []
        for col in range(width):
            in_segment = self._segment_cols[col]
            if col < filled:
                c = sponsor_color if in_segment else progress_color
                char = "█"
            else:
                c = sponsor_dim if in_segment else "#2a2a40"
                char = "░"
            if c != prev_color:
                if run:
                    parts.append(f"[{prev_color}]{''.join(run)}[/{prev_color}]")
                run = [char]
                prev_color = c
            else:
                run.append(char)
        if run and prev_color:
            parts.append(f"[{prev_color}]{''.join(run)}[/{prev_color}]")
        return "".join(parts)

    def _ipc(self, cmd: list) -> None:
        player_mod.send_ipc_command({"command": cmd}, socket_path=self._socket)

    def action_pause_toggle(self) -> None:
        self._ipc(["cycle", "pause"])

    def action_seek(self, seconds: int) -> None:
        self._ipc(["seek", seconds, "relative"])

    def action_seek_pct(self, pct: int) -> None:
        self._ipc(["seek", pct, "absolute-percent"])

    def action_stop(self) -> None:
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
            self.dismiss(False)
        except Exception:
            pass
