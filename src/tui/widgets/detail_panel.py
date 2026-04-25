"""DetailPanel — right panel showing thumbnail, metadata, and embedded player."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.events import Resize, ScreenResume
from textual.widget import Widget
from textual.widgets import Static

from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.thumbnail_widget import ThumbnailWidget

if TYPE_CHECKING:
    from pathlib import Path


def _fmt_duration(secs: int | float | None) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_views(n: int | None) -> str:
    if not n:
        return ""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B views"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K views"
    return f"{n} views"


def _fmt_age(upload_date: str | None) -> str:
    if not upload_date or len(upload_date) < 8:
        return ""
    try:
        import datetime
        y, m, d = int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8])
        delta = datetime.date.today() - datetime.date(y, m, d)
        days = delta.days
        if days < 0:
            return ""
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days}d ago"
        if days < 30:
            return f"{days // 7}w ago"
        if days < 365:
            return f"{days // 30}mo ago"
        return f"{days // 365}y ago"
    except (ValueError, TypeError):
        return ""


class DetailPanel(Widget):
    """Right panel: thumbnail + video metadata + ActionBar (actions or now-playing)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_id: str = ""
        self._last_entry: dict | None = None
        self._thumb_lock = threading.Lock()

    def compose(self) -> ComposeResult:
        with Vertical(id="thumbnail-area"):
            yield ThumbnailWidget(id="thumbnail")
        with ScrollableContainer(id="video-info"):
            yield Static(
                "[dim]↑↓ / jk navigate  ·  ⏎ actions  ·  w watch  ·  l listen  ·  / search[/dim]",
                id="video-title",
                markup=True,
            )
            yield Static("", id="video-channel", markup=True)
            yield Static("", id="video-stats", markup=True)
            yield Static("", id="video-desc-header", markup=True)
            yield Static("", id="video-desc", markup=True)
            yield Static("", id="video-playlists", markup=True)
        yield ActionBar(id="action-bar")

    # ── Action bar proxy ──────────────────────────────────────────────────────

    @property
    def action_bar(self) -> ActionBar:
        return self.query_one("#action-bar", ActionBar)

    def clear(self) -> None:
        self._current_id = ""
        self._last_entry = None
        self.query_one("#thumbnail", ThumbnailWidget).set_placeholder()
        self.query_one("#video-title", Static).update(
            "[dim]↑↓ / jk navigate  ·  ⏎ actions  ·  w watch  ·  l listen  ·  / search[/dim]"
        )
        for wid in ("#video-channel", "#video-stats", "#video-desc-header",
                    "#video-desc", "#video-playlists"):
            self.query_one(wid, Static).update("")

    def update_entry(self, entry: dict) -> None:
        """Update panel with a new video entry."""
        vid = entry.get("id", "")
        self._current_id = vid
        self._last_entry = entry

        thumb = self.query_one("#thumbnail", ThumbnailWidget)
        thumb.set_video_id(vid)
        thumb.set_loading()

        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))

        self.query_one("#video-title", Static).update(
            f"[bold white]{title}[/bold white]"
        )
        self.query_one("#video-channel", Static).update(
            f"[#ff6666]📺 {channel}[/#ff6666]" if channel else ""
        )

        stats_parts = [p for p in [duration, views, age] if p]
        self.query_one("#video-stats", Static).update(
            "  [dim]·[/dim]  ".join(stats_parts)
        )

        desc = entry.get("description", "")
        if desc:
            self._set_description(desc)
        else:
            self.query_one("#video-desc-header", Static).update(
                "[dim]─── Description ──────────────────────────[/dim]"
            )
            self.query_one("#video-desc", Static).update("[dim]Loading…[/dim]")

        self._update_playlists(vid)
        self._render_thumbnail_bg(vid, entry)
        if not desc and not vid.startswith("__"):
            self._fetch_full_meta_bg(vid, entry)
    
    def refresh_metadata(self, entry: dict) -> None:
        """Refresh channel/stats/description from an enriched entry.

        No-op if the entry is not the currently displayed video.
        Does not re-render the thumbnail (avoids flicker on background enrichment).
        """
        if entry.get("id") != self._current_id:
            return
        self._last_entry = entry

        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))

        self.query_one("#video-channel", Static).update(
            f"[#ff6666]📺 {channel}[/#ff6666]" if channel else ""
        )
        stats_parts = [p for p in [duration, views, age] if p]
        self.query_one("#video-stats", Static).update(
            "  [dim]·[/dim]  ".join(stats_parts)
        )
        desc = entry.get("description", "")
        if desc:
            self._set_description(desc)

    def _set_description(self, desc: str) -> None:
        desc = desc.strip()
        if len(desc) > 500:
            desc = desc[:497] + "…"
        self.query_one("#video-desc-header", Static).update(
            "[dim]─── Description ──────────────────────────[/dim]"
        )
        self.query_one("#video-desc", Static).update(f"[dim]{desc}[/dim]")

    def _update_playlists(self, vid: str) -> None:
        if not vid or vid.startswith("__"):
            self.query_one("#video-playlists", Static).update("")
            return
        try:
            from src import playlist
            names = playlist.video_playlists(vid)
            if names:
                joined = "  ".join(f"[#6699cc]♪ {n}[/#6699cc]" for n in names)
                self.query_one("#video-playlists", Static).update(joined)
            else:
                self.query_one("#video-playlists", Static).update("")
        except Exception:
            pass

    # ── Thumbnail re-render on screen resume (fixes disappear after suspend) ──

    def on_screen_resume(self, _: ScreenResume) -> None:
        """Re-render thumbnail when the main screen regains control (e.g. after video)."""
        if self._current_id and self._last_entry:
            self._render_thumbnail_bg(self._current_id, self._last_entry)

    def on_resize(self, event: Resize) -> None:
        if self._current_id and self._last_entry:
            self._render_thumbnail_bg(self._current_id, self._last_entry)

    # ── Background workers ────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="thumbnail")
    def _render_thumbnail_bg(self, vid: str, entry: dict) -> None:
        from src.ui import thumbnail as thumb_mod
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        if _HAS_TEXTUAL_IMAGE:
            local = thumb_mod._thumb_path(vid)
            if not local.exists():
                url = thumb_mod._best_thumb_url(entry)
                if url:
                    local = thumb_mod.download(vid, url) or None  # type: ignore[assignment]
            if local and local.exists():
                self.app.call_from_thread(
                    self.query_one("#thumbnail", ThumbnailWidget).set_image_path, vid, local
                )
            else:
                self.app.call_from_thread(
                    self.query_one("#thumbnail", ThumbnailWidget).set_placeholder
                )
        else:
            # Query the actual dynamic size of the container so chafa fills all available space
            thumb_widget = self.query_one("#thumbnail", ThumbnailWidget)
            cols = thumb_widget.size.width if thumb_widget.size.width > 0 else max(30, (self.size.width or 80) - 4)
            rows = thumb_widget.size.height if thumb_widget.size.height > 0 else 25
            
            config = getattr(self.app, "config", None)
            ansi = thumb_mod.render(vid, entry, cols=cols, rows=rows, config=config)
            self.app.call_from_thread(
                self.query_one("#thumbnail", ThumbnailWidget).set_ansi, vid, ansi
            )

    @work(thread=True, exclusive=True, group="meta")
    def _fetch_full_meta_bg(self, vid: str, entry: dict) -> None:
        try:
            import src.ytdlp as ytdlp
            app = self.app  # type: ignore[attr-defined]
            full = ytdlp.fetch_full(vid, app.config, app.cache)
            if full and self._current_id == vid:
                desc = full.get("description", "")
                if desc:
                    self.app.call_from_thread(self._set_description, desc)
                self.app.call_from_thread(self._update_playlists, vid)
        except Exception:
            pass
