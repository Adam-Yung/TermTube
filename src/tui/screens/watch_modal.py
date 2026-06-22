"""WatchModal — in-TUI video player popup with progress tracking."""

from __future__ import annotations

import os
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.sponsorblock import Segment
from src import logger as _logger


def _fmt_secs(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


class WatchModal(ModalScreen[bool]):
    """
    Video watch screen: launches mpv (with video visible), shows a live progress
    bar in the TUI, and handles keyboard seek/pause/stop via IPC.
    """

    BINDINGS = [
        Binding("space",  "pause_toggle",  "Pause/Resume", show=True),
        Binding("h",      "seek_back",     "−5s",          show=True),
        Binding("l",      "seek_fwd",      "+5s",          show=True),
        Binding("H",      "seek_back_big", "−10s",         show=False),
        Binding("L",      "seek_fwd_big",  "+10s",         show=False),
        Binding("left",   "seek_back",     "−5s",          show=False),
        Binding("right",  "seek_fwd",      "+5s",          show=False),
        Binding("0",      "seek_pct_0",    "0%",           show=False),
        Binding("1",      "seek_pct_10",   "10%",          show=False),
        Binding("2",      "seek_pct_20",   "20%",          show=False),
        Binding("3",      "seek_pct_30",   "30%",          show=False),
        Binding("4",      "seek_pct_40",   "40%",          show=False),
        Binding("5",      "seek_pct_50",   "50%",          show=False),
        Binding("6",      "seek_pct_60",   "60%",          show=False),
        Binding("7",      "seek_pct_70",   "70%",          show=False),
        Binding("8",      "seek_pct_80",   "80%",          show=False),
        Binding("9",      "seek_pct_90",   "90%",          show=False),
        Binding("q",      "stop",          "Stop",         show=True),
        Binding("escape", "stop",          "Stop",         show=False),
    ]

    _SOCKET = None  # Lazy-initialized

    @classmethod
    def _get_socket(cls) -> str:
        if cls._SOCKET is None:
            from src.platform import get_video_ipc_path
            cls._SOCKET = get_video_ipc_path()
        return cls._SOCKET

    def __init__(self, entry: dict, *, ytdl_format: str = "") -> None:
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
        # Pre-computed segment column map for progress bar — invalidated on segments/dur change
        self._segment_cols: list[bool] = []
        self._segment_cols_width: int = 0
        self._segment_cols_dur: float = 0.0

    def compose(self) -> ComposeResult:
        title = self._entry.get("title") or "Unknown"
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="watch-dialog"):
            yield Static("📺  Now playing in mpv", id="np-header")
            yield Static(f"[bold white]{title}[/bold white]", id="np-title", markup=True)
            if channel:
                yield Static(channel, id="np-channel")
            yield Static("", id="np-progress", markup=True)
            yield Static("Loading…", id="np-time")
            yield Static(
                "[dim]space[/dim] pause  "
                "[dim]h/l[/dim] ±5s  "
                "[dim]H/L[/dim] ±10s  "
                "[dim]0–9[/dim] seek%  "
                "[dim]q[/dim] stop",
                id="np-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        import time
        self._buffering_since = time.monotonic()
        self._launch_video()
        self._poll_timer = self.set_interval(0.5, self._poll_mpv)

    # ── Background mpv launcher ───────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="video_player")
    def _launch_video(self) -> None:
        from src import player as player_mod

        vid = self._entry.get("id", "")
        if vid and hasattr(self.app, "cache") and hasattr(self.app.cache, "suppress_video"):
            self.app.cache.suppress_video(vid)

        # Fetch SponsorBlock segments
        config = getattr(self.app, "config", None)
        if config and config.sponsorblock_enabled and vid:
            from src.sponsorblock import fetch_segments
            self._segments = fetch_segments(vid, config.sponsorblock_categories)
            self._segments.sort(key=lambda s: s.start)
            self._sb_next_idx = 0
            self._segment_cols = []  # invalidate pre-computed bar cache

        url = (
            self._entry.get("_local_path")
            or f"https://www.youtube.com/watch?v={vid}"
        )
        title = self._entry.get("title", "")

        cookie_args = config.cookie_args() if config else []

        # Pre-resolve the direct stream URL using bundled yt-dlp so mpv doesn't
        # need to spawn its own yt-dlp via ytdl_hook (saves 2-5s startup delay).
        resolved_urls: list[str] | None = None
        if not self._entry.get("_local_path") and vid and config:
            import src.ytdlp as ytdlp
            fmt = self._ytdl_format or "bv+(ba[format_note*=original]/ba)"
            resolved_urls = ytdlp.resolve_stream_url(vid, config, format_spec=fmt)
            if resolved_urls:
                _logger.debug("video pre-resolved %d URL(s) for %s", len(resolved_urls), vid)

        mpv_exe = player_mod._mpv_exe()
        if not mpv_exe:
            from src.platform import install_hint
            self.app.call_from_thread(
                self.app.notify,
                f"mpv not found — install with: {install_hint('mpv')}",
                severity="error",
            )
            self.app.call_from_thread(self.dismiss, False)
            return

        input_conf = player_mod._write_input_conf()
        cmd = [
            mpv_exe,
            f"--input-conf={input_conf}",
            f"--input-ipc-server={self._get_socket()}",
            "--no-terminal",
            "--really-quiet",
            "--msg-level=all=no",
        ]
        if title:
            cmd += [f"--title={title}", f"--force-media-title={title}"]
        if resolved_urls:
            cmd += ["--no-ytdl", "--"]
            cmd += resolved_urls
        else:
            if self._ytdl_format:
                cmd += [f"--ytdl-format={self._ytdl_format}"]
            else:
                cmd += ["--ytdl-format=bv+(ba[format_note*=original]/ba)"]
            ytdl_raw = player_mod._cookie_args_to_ytdl_raw(cookie_args)
            if ytdl_raw:
                cmd += [f"--ytdl-raw-options={ytdl_raw}"]
            cmd += ["--", url]

        try:
            from src.platform import get_popen_kwargs, ProcessRegistry
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **get_popen_kwargs(headless=False),
            )
            ProcessRegistry.get().register(self._proc)
        except FileNotFoundError:
            from src.platform import install_hint
            self.app.call_from_thread(
                self.app.notify,
                f"mpv not found — install with: {install_hint('mpv')}",
                severity="error",
            )
            self.app.call_from_thread(self.dismiss, False)
            return
        except OSError as exc:
            self.app.call_from_thread(
                self.app.notify, f"Failed to launch mpv: {exc}", severity="error"
            )
            self.app.call_from_thread(self.dismiss, False)
            return

        from src import history
        history.add(self._entry)

        try:
            self._proc.wait()
        finally:
            from src.platform import ProcessRegistry
            ProcessRegistry.get().unregister(self._proc)
        try:
            os.unlink(input_conf)
        except OSError:
            pass
        from src.player import close_persistent_socket
        close_persistent_socket(self._get_socket())
        from src.platform import cleanup_ipc
        cleanup_ipc(self._get_socket())

        if not self._stopped:
            try:
                self.app.call_from_thread(self.dismiss, True)
            except Exception:
                pass
            if title:
                try:
                    self.app.call_from_thread(
                        self.app.notify, f"✓ Finished: {title[:50]}", timeout=4
                    )
                except Exception:
                    pass

    # ── IPC polling ───────────────────────────────────────────────────────────

    def _poll_mpv(self) -> None:
        # Auto-dismiss if the user manually closes the external mpv window
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
        from src.player import poll_audio_properties

        pos, dur, paused = poll_audio_properties(socket_path=self._get_socket())
        if pos is not None and dur and float(dur) > 0:
            pos_f = float(pos)
            dur_f = float(dur)
            self._dur = dur_f

            # Auto-skip sponsor segments — O(1) via sorted pointer
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
                            f"Skipped: {seg.category} ({skip_dur}s)",
                            timeout=3,
                        )
                        return

            def _update_ui():
                try:
                    bar_width = max(8, (self.query_one("#watch-dialog").size.width or 60) - 6)
                    self.query_one("#np-progress", Static).update(
                        self._render_bar(pos_f, dur_f, bar_width)
                    )
                    pause_indicator = "  ⏸ paused" if paused else ""
                    self.query_one("#np-time", Static).update(
                        f"{_fmt_secs(pos_f)}  /  {_fmt_secs(dur_f)}{pause_indicator}"
                    )
                except Exception:
                    pass

            self.app.call_from_thread(_update_ui)
        elif self._buffering_since > 0:
            import time as time_mod
            wait_s = int(time_mod.monotonic() - self._buffering_since)
            buf_text = f"Buffering… ({wait_s}s)" if wait_s > 0 else "Buffering…"
            def _update_buf():
                try:
                    self.query_one("#np-time", Static).update(buf_text)
                except Exception:
                    pass
            self.app.call_from_thread(_update_buf)

    # ── Progress bar rendering ─────────────────────────────────────────────

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

        # Rebuild segment column map only when width or duration changes
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

    # ── IPC helper ────────────────────────────────────────────────────────────

    def _ipc(self, cmd: list) -> None:
        from src.player import send_ipc_command
        send_ipc_command({"command": cmd}, socket_path=self._get_socket())

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_pause_toggle(self) -> None:
        self._ipc(["cycle", "pause"])

    def action_seek_back(self) -> None:
        self._ipc(["seek", -5, "relative"])

    def action_seek_fwd(self) -> None:
        self._ipc(["seek", 5, "relative"])

    def action_seek_back_big(self) -> None:
        self._ipc(["seek", -10, "relative"])

    def action_seek_fwd_big(self) -> None:
        self._ipc(["seek", 10, "relative"])

    def _seek_pct(self, pct: int) -> None:
        self._ipc(["seek", pct, "absolute-percent"])

    def action_seek_pct_0(self)  -> None: self._seek_pct(0)
    def action_seek_pct_10(self) -> None: self._seek_pct(10)
    def action_seek_pct_20(self) -> None: self._seek_pct(20)
    def action_seek_pct_30(self) -> None: self._seek_pct(30)
    def action_seek_pct_40(self) -> None: self._seek_pct(40)
    def action_seek_pct_50(self) -> None: self._seek_pct(50)
    def action_seek_pct_60(self) -> None: self._seek_pct(60)
    def action_seek_pct_70(self) -> None: self._seek_pct(70)
    def action_seek_pct_80(self) -> None: self._seek_pct(80)
    def action_seek_pct_90(self) -> None: self._seek_pct(90)

    def action_stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        self._ipc(["quit"])
        from src.platform import terminate_process, ProcessRegistry
        terminate_process(self._proc, timeout=2.0)
        if self._proc:
            ProcessRegistry.get().unregister(self._proc)
        try:
            self.dismiss(False)
        except Exception:
            pass
