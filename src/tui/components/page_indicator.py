"""TermTube v2 — page indicator widget.

Renders:   ◀  Page 3 / 7  ▶
Click on ◀ or ▶ to navigate pages.
Shows a spinner while the next page is prefetching.
"""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

THEME_COLORS = {
    "crimson":  "#ff4444",
    "amber":    "#e8820c",
    "ocean":    "#0ea5e9",
    "midnight": "#a855f7",
    "forest":   "#22c55e",
}


class PageIndicator(Widget):
    """◀  Page N / M  ▶  with click navigation."""

    DEFAULT_CSS = """
    PageIndicator {
        height: 1;
        content-align: center middle;
    }
    """

    class PrevPage(Message):
        pass

    class NextPage(Message):
        pass

    current: reactive[int] = reactive(1)
    total: reactive[int] = reactive(1)
    prefetching: reactive[bool] = reactive(False)

    def __init__(self, theme: str = "crimson", **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")

    def set_theme(self, theme: str) -> None:
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        self.refresh()

    def render(self) -> Text:
        color = self._theme_color
        text = Text(no_wrap=True, justify="center")

        prev_style = Style(color=color, bold=True) if self.current > 1 else Style(dim=True)
        text.append("◀", style=prev_style)
        text.append("  ")

        text.append("Page ", style="dim")
        text.append(str(self.current), style=Style(color=color, bold=True))
        text.append(" / ", style="dim")
        text.append(str(self.total), style="dim")

        if self.prefetching:
            text.append("  ⟳", style=Style(color=color, dim=True))
        else:
            text.append("  ")

        next_style = Style(color=color, bold=True) if self.current < self.total else Style(dim=True)
        text.append("▶", style=next_style)

        return text

    def on_click(self, event) -> None:
        width = self.size.width or 1
        x = event.x
        # Left third = prev, right third = next
        if x < width // 3 and self.current > 1:
            self.post_message(self.PrevPage())
        elif x > width * 2 // 3 and self.current < self.total:
            self.post_message(self.NextPage())

    def watch_current(self, _: int) -> None:
        self.refresh()

    def watch_total(self, _: int) -> None:
        self.refresh()

    def watch_prefetching(self, _: bool) -> None:
        self.refresh()
