"""TermTube v2 — persistent MiniPlayer bar.

Always mounted at the bottom of the screen regardless of active tab.
Handles both audio and video playback state through PlayerSession events.

Idle mode  (height 1): "♫  No media playing  |  l to listen · w to watch"
Playing mode (height 7):
  Line 1: [AUDIO] or [VIDEO]  Title — Channel
  Line 2: ProgressBar (seekable, with SB ticks and bookmark ticks)
  Line 3: 00:00 / 00:00  (██░░░░  57%)
  Line 4: Vol: 80  |  ▶/⏸  |  Queue: 2 tracks
  Line 5: h -5s  H -30s  l +5s  L +30s  Space pause  s stop  m bookmark
"""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tui.components.progress_bar import ProgressBar, _fmt_time

THEME_COLORS = {
    "crimson":  "#ff4444",
    "amber":    "#e8820c",
    "ocean":    "#0ea5e9",
    "midnight": "#a855f7",
    "forest":   "#22c55e",
}


class MiniPlayer(Widget):
    """Persistent bottom player bar — always visible."""

    DEFAULT_CSS = """
    MiniPlayer {
        dock: bottom;
        height: 2;
        border-top: solid $accent;
        background: $surface;
        padding: 0 1;
    }
    MiniPlayer.--playing {
        height: 8;
    }
    #mp-idle {
        height: 1;
        content-align: center middle;
        color: $text-muted;
    }
    #mp-mode-badge {
        height: 1;
    }
    #mp-title {
        height: 1;
        overflow: hidden;
    }
    #mp-progress {
        height: 1;
    }
    #mp-time {
        height: 1;
    }
    #mp-controls {
        height: 1;
        color: $text-muted;
    }
    #mp-hints {
        height: 1;
        color: $text-disabled;
    }
    """

    # Messages
    class SeekRequested(Message):
        def __init__(self, fraction: float) -> None:
            super().__init__()
            self.fraction = fraction

    class VolumeChangeRequested(Message):
        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    def __init__(self, theme: str = "crimson", **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        self._playing = False
        self._mode = ""           # "AUDIO" or "VIDEO"
        self._title = ""
        self._channel = ""
        self._position = 0.0
        self._duration = 0.0
        self._paused = False
        self._volume = 100
        self._queue_len = 0
        self._segments: list[dict] = []
        self._bookmarks: list[float] = []

    def compose(self) -> ComposeResult:
        yield Static("♫  No media playing  ·  l to listen  ·  w to watch", id="mp-idle")
        yield Static("", id="mp-mode-badge")
        yield Static("", id="mp-title")
        yield ProgressBar(id="mp-progress")
        yield Static("", id="mp-time")
        yield Static("", id="mp-controls")
        yield Static(
            "h -5s  H -30s  l +5s  L +30s  Space pause/resume  [ ] vol  s stop  m bookmark",
            id="mp-hints",
        )

    def on_mount(self) -> None:
        self._set_idle()

    # ------------------------------------------------------------------
    # Public update API  (called from main_screen worker via call_from_thread)
    # ------------------------------------------------------------------

    def set_idle(self) -> None:
        self._playing = False
        self._mode = ""
        self.remove_class("--playing")
        self._set_idle()

    def set_playing(
        self,
        *,
        mode: str,
        title: str,
        channel: str,
        volume: int = 100,
        queue_len: int = 0,
        segments: list[dict] | None = None,
        bookmarks: list[float] | None = None,
    ) -> None:
        self._playing = True
        self._mode = mode
        self._title = title
        self._channel = channel
        self._volume = volume
        self._queue_len = queue_len
        self._segments = segments or []
        self._bookmarks = bookmarks or []
        self.add_class("--playing")

        pb = self.query_one("#mp-progress", ProgressBar)
        pb.set_theme_color(self._theme_color)
        pb.set_segments(self._segments)
        pb.set_bookmarks(self._bookmarks)

        self._refresh_playing()

    def update_position(self, position: float, duration: float, paused: bool) -> None:
        self._position = position
        self._duration = duration
        self._paused = paused
        if not self._playing:
            return
        pb = self.query_one("#mp-progress", ProgressBar)
        pb.position = position
        pb.duration = duration
        self._refresh_time()
        self._refresh_controls()

    def update_volume(self, volume: int) -> None:
        self._volume = volume
        if self._playing:
            self._refresh_controls()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        if self._playing:
            pb = self.query_one("#mp-progress", ProgressBar)
            pb.set_theme_color(self._theme_color)
            self._refresh_playing()

    def update_queue(self, queue_len: int) -> None:
        self._queue_len = queue_len
        if self._playing:
            self._refresh_controls()

    # ------------------------------------------------------------------
    # Internal render helpers
    # ------------------------------------------------------------------

    def _set_idle(self) -> None:
        try:
            self.query_one("#mp-idle", Static).display = True
            for wid in ("#mp-mode-badge", "#mp-title", "#mp-progress",
                        "#mp-time", "#mp-controls", "#mp-hints"):
                self.query_one(wid).display = False
        except Exception:
            pass

    def _refresh_playing(self) -> None:
        try:
            self.query_one("#mp-idle", Static).display = False
            for wid in ("#mp-mode-badge", "#mp-title", "#mp-progress",
                        "#mp-time", "#mp-controls", "#mp-hints"):
                self.query_one(wid).display = True
        except Exception:
            pass

        color = self._theme_color
        try:
            badge = Text()
            badge.append(f" {self._mode} ", style=Style(color="black", bgcolor=color, bold=True))
            self.query_one("#mp-mode-badge", Static).update(badge)

            title_text = Text(overflow="ellipsis", no_wrap=True)
            title_text.append(f" {self._title}", style=Style(color=color, bold=True))
            if self._channel:
                title_text.append(f"  —  {self._channel}", style="dim")
            self.query_one("#mp-title", Static).update(title_text)
        except Exception:
            pass

        self._refresh_time()
        self._refresh_controls()

    def _refresh_time(self) -> None:
        try:
            pos_s = _fmt_time(self._position)
            dur_s = _fmt_time(self._duration)
            pct = int(self._position / self._duration * 100) if self._duration > 0 else 0
            time_text = Text()
            time_text.append(f" {pos_s}", style=Style(color=self._theme_color))
            time_text.append(f" / {dur_s}", style="dim")
            time_text.append(f"  {pct}%", style="dim")
            self.query_one("#mp-time", Static).update(time_text)
        except Exception:
            pass

    def _refresh_controls(self) -> None:
        try:
            paused_icon = "⏸" if self._paused else "▶"
            ctrl = Text()
            ctrl.append(f" {paused_icon}", style=Style(color=self._theme_color, bold=True))
            ctrl.append("  Vol: ", style="dim")
            ctrl.append(str(self._volume), style=Style(color=self._theme_color))
            if self._queue_len > 0:
                ctrl.append(f"  |  Queue: {self._queue_len}", style="dim")
            self.query_one("#mp-controls", Static).update(ctrl)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_progress_bar_seeked(self, event: ProgressBar.Seeked) -> None:
        self.post_message(self.SeekRequested(event.position))
