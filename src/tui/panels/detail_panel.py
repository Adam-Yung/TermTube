"""TermTube v2 — DetailPanel (passive, reactive).

Right panel that displays full metadata + thumbnail for the focused video.
All data is pushed in by the screen via reactive attributes or direct calls.
The panel never fetches anything itself.

Channel name is a clickable link that posts ChannelRequested.
Bookmarks are listed below the description.
"""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.containers import ScrollableContainer
from textual.widgets import Static

from tui.components.thumbnail import ThumbnailWidget


class DetailPanel(Widget):

    DEFAULT_CSS = """
    DetailPanel {
        width: 55%;
        padding: 0 1;
    }
    ThumbnailWidget {
        height: 16;
        margin-bottom: 1;
    }
    #dp-title {
        height: auto;
        color: white;
        text-style: bold;
        margin-bottom: 0;
    }
    #dp-channel {
        height: 1;
        margin-bottom: 1;
    }
    #dp-stats {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
    }
    #dp-desc {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #dp-bookmarks {
        height: auto;
        margin-bottom: 1;
    }
    #dp-playlists {
        height: 1;
        color: $text-muted;
    }
    ScrollableContainer {
        height: 1fr;
    }
    """

    class ChannelRequested(Message):
        def __init__(self, channel_url: str, channel_name: str) -> None:
            super().__init__()
            self.channel_url = channel_url
            self.channel_name = channel_name

    def __init__(self, theme: str = "crimson", **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme = theme
        self._theme_color = "#ff4444"
        self._current_entry: dict | None = None

    def compose(self) -> ComposeResult:
        yield ThumbnailWidget(id="dp-thumb")
        with ScrollableContainer():
            yield Static("", id="dp-title")
            yield Static("", id="dp-channel")
            yield Static("", id="dp-stats")
            yield Static("", id="dp-desc")
            yield Static("", id="dp-bookmarks")
            yield Static("", id="dp-playlists")

    # ------------------------------------------------------------------
    # Public API (called by screen)
    # ------------------------------------------------------------------

    def update_basic(self, entry: dict) -> None:
        """Instant update from flat/cached entry data."""
        self._current_entry = entry
        self._render_title(entry)
        self._render_channel(entry)
        self._render_stats(entry)
        self._render_desc(entry.get("description", ""))
        self._render_bookmarks(entry.get("id", ""))
        self._render_playlists(entry.get("id", ""))
        thumb = self.query_one("#dp-thumb", ThumbnailWidget)
        thumb.set_video_id(entry.get("id", ""))

    def refresh_metadata(self, entry: dict) -> None:
        """Update with full metadata (channel, stats, description)."""
        self._current_entry = entry
        self._render_channel(entry)
        self._render_stats(entry)
        self._render_desc(entry.get("description", ""))
        self._render_bookmarks(entry.get("id", ""))

    def set_thumbnail_loading(self) -> None:
        self.query_one("#dp-thumb", ThumbnailWidget).set_loading()

    def set_thumbnail_placeholder(self) -> None:
        self.query_one("#dp-thumb", ThumbnailWidget).set_placeholder()

    def set_thumbnail(self, video_id: str) -> None:
        self.query_one("#dp-thumb", ThumbnailWidget).set_video_id(video_id)

    def clear(self) -> None:
        self._current_entry = None
        for wid in ("#dp-title", "#dp-channel", "#dp-stats", "#dp-desc",
                    "#dp-bookmarks", "#dp-playlists"):
            try:
                self.query_one(wid, Static).update("")
            except Exception:
                pass

    def set_theme(self, theme: str) -> None:
        from tui.components.mini_player import THEME_COLORS
        self._theme = theme
        self._theme_color = THEME_COLORS.get(theme, "#ff4444")
        if self._current_entry:
            self.update_basic(self._current_entry)

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _render_title(self, entry: dict) -> None:
        title = entry.get("title") or entry.get("fulltitle") or "(no title)"
        try:
            self.query_one("#dp-title", Static).update(Text(title, style="bold white"))
        except Exception:
            pass

    def _render_channel(self, entry: dict) -> None:
        channel = entry.get("channel") or entry.get("uploader") or ""
        channel_url = entry.get("channel_url") or entry.get("uploader_url") or ""
        color = self._theme_color or "#ff4444"
        text = Text(no_wrap=True)
        if channel:
            text.append(channel, style=Style(color=color, bold=True, link=channel_url or None))
        try:
            self.query_one("#dp-channel", Static).update(text)
        except Exception:
            pass

    def _render_stats(self, entry: dict) -> None:
        from tui.components.video_card import _fmt_views, _fmt_duration, _fmt_age
        parts = []
        dur = _fmt_duration(entry.get("duration"))
        if dur:
            parts.append(dur)
        views = _fmt_views(entry.get("view_count"))
        if views:
            parts.append(views)
        age = _fmt_age(entry.get("upload_date") or entry.get("timestamp"))
        if age:
            parts.append(age)
        likes = entry.get("like_count")
        if likes:
            parts.append(f"♥ {likes:,}")
        text = "  ·  ".join(parts)
        try:
            self.query_one("#dp-stats", Static).update(Text(text, style="dim"))
        except Exception:
            pass

    def _render_desc(self, desc: str) -> None:
        trimmed = (desc or "").strip()
        if len(trimmed) > 500:
            trimmed = trimmed[:497] + "…"
        try:
            self.query_one("#dp-desc", Static).update(Text(trimmed, style="dim"))
        except Exception:
            pass

    def _render_bookmarks(self, video_id: str) -> None:
        import history as _history
        from tui.components.progress_bar import _fmt_time
        try:
            bms = _history.get_bookmarks(video_id)
            if not bms:
                self.query_one("#dp-bookmarks", Static).update("")
                return
            color = self._theme_color or "#ff4444"
            text = Text()
            text.append("Bookmarks: ", style=Style(bold=True, color=color))
            for i, bm in enumerate(bms):
                if i:
                    text.append("  ")
                text.append(f"◆ {_fmt_time(bm['position'])}", style=Style(color=color))
                if bm.get("label"):
                    text.append(f" {bm['label']}", style="dim")
            self.query_one("#dp-bookmarks", Static).update(text)
        except Exception:
            pass

    def _render_playlists(self, video_id: str) -> None:
        import playlist as _playlist
        try:
            names = _playlist.video_playlists(video_id)
            if not names:
                self.query_one("#dp-playlists", Static).update("")
                return
            text = Text()
            text.append("Playlists: ", style="dim")
            text.append(", ".join(names), style="dim")
            self.query_one("#dp-playlists", Static).update(text)
        except Exception:
            pass

    def on_click(self, event) -> None:
        # Channel name click
        if self._current_entry:
            channel_url = self._current_entry.get("channel_url") or ""
            channel = self._current_entry.get("channel") or ""
            if channel_url and channel:
                self.post_message(self.ChannelRequested(channel_url, channel))
