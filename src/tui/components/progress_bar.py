"""TermTube v2 — seekable animated progress bar widget.

Features:
  - Click-to-seek via mouse events
  - SponsorBlock segment tick marks (colored)
  - Bookmark tick marks (different color)
  - Smooth animation driven by PlayerSession property events
"""
from __future__ import annotations

from typing import Callable

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget


class ProgressBar(Widget):
    """A horizontal progress bar with segment markers and click-to-seek."""

    DEFAULT_CSS = """
    ProgressBar {
        height: 1;
        width: 100%;
    }
    """

    class Seeked(Message):
        """Emitted when user clicks the bar."""
        def __init__(self, position: float) -> None:
            super().__init__()
            self.position = position  # 0.0–1.0

    position: reactive[float] = reactive(0.0)
    duration: reactive[float] = reactive(0.0)

    def __init__(
        self,
        *,
        filled_char: str = "█",
        empty_char: str = "░",
        sb_char: str = "▓",
        bookmark_char: str = "◆",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._filled = filled_char
        self._empty = empty_char
        self._sb_char = sb_char
        self._bookmark_char = bookmark_char
        self._segments: list[dict] = []      # SponsorBlock segments
        self._bookmarks: list[float] = []    # bookmark positions (seconds)
        self._theme_color = "#ff4444"

    def set_segments(self, segments: list[dict]) -> None:
        self._segments = segments
        self.refresh()

    def set_bookmarks(self, positions: list[float]) -> None:
        self._bookmarks = positions
        self.refresh()

    def set_theme_color(self, color: str) -> None:
        self._theme_color = color
        self.refresh()

    def render(self) -> Text:
        width = self.size.width or 40
        pos = self.position
        dur = self.duration

        text = Text(no_wrap=True, overflow="fold")

        if dur <= 0:
            text.append(self._empty * width, style="dim")
            return text

        filled = int((pos / dur) * width)

        # Build the bar char by char
        for i in range(width):
            frac = i / width
            cell_secs = frac * dur

            # Check if this cell is a bookmark
            is_bookmark = any(
                abs(cell_secs - b) < (dur / width * 1.5) for b in self._bookmarks
            )
            # Check if this cell falls in a SponsorBlock segment
            sb_color: str | None = None
            for seg in self._segments:
                if seg["start"] <= cell_secs <= seg["end"]:
                    from sponsorblock import CATEGORY_COLORS
                    sb_color = CATEGORY_COLORS.get(seg.get("category", ""), "#00cc00")
                    break

            if is_bookmark:
                text.append(self._bookmark_char, style=Style(color="#ffd700", bold=True))
            elif sb_color:
                text.append(self._sb_char, style=Style(color=sb_color))
            elif i < filled:
                text.append(self._filled, style=Style(color=self._theme_color))
            else:
                text.append(self._empty, style="dim")

        return text

    def on_click(self, event) -> None:
        width = self.size.width or 1
        x = event.x
        frac = max(0.0, min(1.0, x / width))
        self.post_message(self.Seeked(frac))

    def watch_position(self, value: float) -> None:
        self.refresh()

    def watch_duration(self, value: float) -> None:
        self.refresh()


def _fmt_time(secs: float) -> str:
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
