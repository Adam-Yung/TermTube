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

    def __init__(self, entry: dict, *, ytdl_format: str = "", stream_urls: dict | None = None) -> None:
        super().__init__()
        self._entry = entry
        self._ytdl_format = ytdl_format
        self._stream_urls = stream_urls
        self._proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._stopped = False
        self._segments: list[Segment] = []
        self._skipped_indices: set[int] = set()
        self._dur: float = 0.0

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
        self._launch_video()
        self.set_interval(0.5, self._poll_mpv)

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

        url = (
            self._entry.get("_local_path")
            or f"https://www.youtube.com/watch?v={vid}"
        )
        title = self._entry.get("title", "")

        cookie_args = config.cookie_args if config else []

        # Use prefetched stream URLs if available, not expired, and no custom quality
        use_prefetched = False
        audio_file_url: str | None = None
        if not self._entry.get("_local_path") and not self._ytdl_format and self._stream_urls:
            import time
            expire = self._stream_urls.get("expire", 0)
            fetched_at = self._stream_urls.get("fetched_at", 0)
            is_fresh = (
                (not expire or (expire - time.time()) >= 300)
                and (not fetched_at or (time.time() - fetched_at) <= 18000)
            )
            if is_fresh:
                video_url = self._stream_urls.get("video_url")
                audio_url = self._stream_urls.get("audio_url")
                if video_url:
                    url = video_url
                    audio_file_url = audio_url
                    use_prefetched = True

        input_conf = player_mod._write_input_conf()
        cmd = [
            "mpv",
            f"--input-conf={input_conf}",
            f"--input-ipc-server={self._get_socket()}",
            "--no-terminal",
            "--really-quiet",
            "--msg-level=all=no",
        ]
        if title:
            cmd += [f"--title={title}"]
        if self._ytdl_format:
            cmd += [f"--ytdl-format={self._ytdl_format}"]
        if use_prefetched and audio_file_url:
            cmd += [f"--audio-file={audio_file_url}"]
        if not use_prefetched:
            ytdl_raw = player_mod._cookie_args_to_ytdl_raw(cookie_args)
            if ytdl_raw:
                cmd += [f"--ytdl-raw-options={ytdl_raw}"]
        cmd += ["--", url]

        try:
            from src.platform import get_popen_kwargs
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **get_popen_kwargs(headless=False),
            )
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
            try:
                os.unlink(input_conf)
            except OSError:
                pass
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

        from src.player import poll_audio_properties

        pos, dur, paused = poll_audio_properties(socket_path=self._get_socket())
        if pos is not None and dur and float(dur) > 0:
            pos_f = float(pos)
            dur_f = float(dur)
            self._dur = dur_f

            # Auto-skip sponsor segments
            config = getattr(self.app, "config", None)
            if config and config.sponsorblock_auto_skip and self._segments:
                for i, seg in enumerate(self._segments):
                    if i in self._skipped_indices:
                        continue
                    if seg.start <= pos_f < seg.end:
                        self._skipped_indices.add(i)
                        skip_dur = int(seg.end - seg.start)
                        self._ipc(["seek", seg.end, "absolute"])
                        self.notify(
                            f"Skipped: {seg.category} ({skip_dur}s)",
                            timeout=3,
                        )
                        return

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

        parts: list[str] = []
        for col in range(width):
            t = (col / width) * dur
            in_segment = any(s.start <= t < s.end for s in self._segments)
            if col < filled:
                c = sponsor_color if in_segment else progress_color
                parts.append(f"[{c}]█[/{c}]")
            else:
                c = sponsor_dim if in_segment else "#2a2a40"
                parts.append(f"[{c}]░[/{c}]")
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
        self._ipc(["quit"])
        from src.platform import terminate_process
        terminate_process(self._proc, timeout=2.0)
        try:
            self.dismiss(False)
        except Exception:
            pass
