"""TermTube v2 — AppHeader widget.

Displays: [TermTube]  [clock]  [spinner]  [cookie status dot]
"""
from __future__ import annotations

import time

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from cookies import CookieStatus

THEME_COLORS = {
    "crimson":  "#ff4444",
    "amber":    "#e8820c",
    "ocean":    "#0ea5e9",
    "midnight": "#a855f7",
    "forest":   "#22c55e",
}

_COOKIE_COLORS: dict[CookieStatus, str] = {
    "ok":      "#22c55e",
    "stale":   "#f59e0b",
    "missing": "#ef4444",
}


class AppHeader(Widget):
    """Top bar: title · clock · spinner · cookie dot."""

    DEFAULT_CSS = """
    AppHeader {
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    loading: reactive[bool] = reactive(False)
    cookie_status: reactive[str] = reactive("missing")

    def __init__(self, theme: str = "crimson", **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def set_loading(self, loading: bool) -> None:
        self.loading = loading

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        self.refresh()

    def render(self) -> Text:
        color = self._theme_color
        text = Text(no_wrap=True)

        text.append(" TermTube ", style=Style(bold=True, color="white"))
        text.append("v2  ", style=Style(dim=True))

        # Clock
        clock = time.strftime("%H:%M")
        text.append(clock, style=Style(dim=True))

        # Spinner
        if self.loading:
            spinners = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            frame = spinners[int(time.time() * 10) % len(spinners)]
            text.append(f"  {frame}", style=Style(color=color))
        else:
            text.append("   ", style="dim")

        # Cookie status dot
        dot_color = _COOKIE_COLORS.get(self.cookie_status, "#ef4444")  # type: ignore[arg-type]
        text.append("●", style=Style(color=dot_color))
        label_map = {"ok": "cookies ok", "stale": "cookies stale", "missing": "no cookies"}
        text.append(
            f" {label_map.get(self.cookie_status, '')}",
            style=Style(color=dot_color, dim=True),
        )

        return text

    def watch_loading(self, _: bool) -> None:
        self.refresh()

    def watch_cookie_status(self, _: str) -> None:
        self.refresh()
