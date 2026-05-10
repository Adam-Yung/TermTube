"""TermTube v2 — VideoCard list item widget.

Displays:
  Line 1: [color-strip] Title (truncated)  [badge: ↓V ↓A ●watched]
  Line 2:               Channel · Duration · Views · Age

The color-strip is an 8-char wide thumbnail mosaic from the JPEG cache.
Compact mode (< 80 cols) omits the strip and collapses to 2 tight lines.
"""
from __future__ import annotations

import time

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ListItem, Static

from tui.components.thumbnail import build_strip

THEME_COLORS = {
    "crimson":  "#ff4444",
    "amber":    "#e8820c",
    "ocean":    "#0ea5e9",
    "midnight": "#a855f7",
    "forest":   "#22c55e",
}


def _fmt_views(n: int | None) -> str:
    if n is None:
        return ""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n//1_000}K views"
    return f"{n} views"


def _fmt_duration(secs: int | float | None) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_age(ts: str | int | None) -> str:
    """Convert upload_date (YYYYMMDD) or timestamp to relative age."""
    if not ts:
        return ""
    try:
        if isinstance(ts, str) and len(ts) == 8:
            import datetime
            d = datetime.datetime(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
            delta = datetime.datetime.now() - d
            days = delta.days
        else:
            days = int((time.time() - float(ts)) / 86400)
        if days < 1:
            return "today"
        if days < 7:
            return f"{days}d ago"
        if days < 30:
            return f"{days//7}w ago"
        if days < 365:
            return f"{days//30}mo ago"
        return f"{days//365}y ago"
    except Exception:
        return ""


class VideoCard(ListItem):
    """A rich list item for a single video entry."""

    def __init__(
        self,
        entry: dict,
        *,
        theme: str = "crimson",
        watched: bool = False,
        has_video: bool = False,
        has_audio: bool = False,
        compact: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._entry = entry
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        self._watched = watched
        self._has_video = has_video
        self._has_audio = has_audio
        self._compact = compact
        self._vid = entry.get("id", "")

    @property
    def entry(self) -> dict:
        return self._entry

    @property
    def video_id(self) -> str:
        return self._vid

    def compose(self) -> ComposeResult:
        yield Static(self._render_line1(), id="vc-line1")
        yield Static(self._render_line2(), id="vc-line2")

    def update_entry(self, entry: dict) -> None:
        self._entry = entry
        self._vid = entry.get("id", self._vid)
        try:
            self.query_one("#vc-line1", Static).update(self._render_line1())
            self.query_one("#vc-line2", Static).update(self._render_line2())
        except Exception:
            pass

    def set_watched(self, watched: bool) -> None:
        if watched != self._watched:
            self._watched = watched
            try:
                self.query_one("#vc-line1", Static).update(self._render_line1())
            except Exception:
                pass

    def _render_line1(self) -> Text:
        e = self._entry
        title = str(e.get("title") or e.get("fulltitle") or "(no title)")
        color = self._theme_color

        text = Text(no_wrap=True, overflow="ellipsis")

        if not self._compact:
            strip = build_strip(self._vid, width=8)
            text.append_text(strip)
            text.append(" ")

        text.append(title, style=Style(bold=True, color="white"))
        text.append(" ")

        # Badges
        if self._has_video:
            text.append("↓V", style=Style(color=color, bold=True))
            text.append(" ")
        if self._has_audio:
            text.append("↓A", style=Style(color=color, bold=True))
            text.append(" ")
        if self._watched:
            text.append("●", style=Style(color=color))

        return text

    def _render_line2(self) -> Text:
        e = self._entry
        color = self._theme_color
        parts = []

        channel = e.get("channel") or e.get("uploader") or e.get("uploader_id", "")
        if channel:
            parts.append(("channel", channel, Style(color=color)))

        dur = _fmt_duration(e.get("duration"))
        if dur:
            parts.append(("dur", dur, Style(color="white", dim=True)))

        views = _fmt_views(e.get("view_count"))
        if views:
            parts.append(("views", views, Style(dim=True)))

        age = _fmt_age(e.get("upload_date") or e.get("timestamp"))
        if age:
            parts.append(("age", age, Style(dim=True)))

        indent = " " if self._compact else "         "
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(indent)
        for i, (_, val, style) in enumerate(parts):
            text.append(val, style=style)
            if i < len(parts) - 1:
                text.append("  ·  ", style=Style(dim=True))

        return text
