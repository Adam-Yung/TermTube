"""DetailPanel — right panel showing thumbnail, metadata, and embedded player.

This panel is a *passive view*: it does not start any background workers.
The owning screen (MainScreen) drives focus and thumbnail rendering with
debounced workers and pushes results in via the public methods below
(`update_basic`, `set_description`, `set_thumbnail_*`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.events import Resize, ScreenResume
from textual.message import Message
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
    """Right panel: thumbnail + video metadata + ActionBar (actions or now-playing).

    Passive — the owning screen pushes content in.
    """

    class RerenderRequested(Message):
        """Posted on resize/screen-resume so the screen can re-trigger thumbnail render."""

        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_id: str = ""
        self._last_entry: dict | None = None

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

    @property
    def current_id(self) -> str:
        return self._current_id

    @property
    def last_entry(self) -> dict | None:
        return self._last_entry

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

    # ── Public update API (called from MainScreen) ────────────────────────────

    def update_basic(self, entry: dict) -> None:
        """Synchronously paint title / channel / stats / playlists from cached entry.

        Called immediately on cursor move. Does not start any workers.
        Description is left as 'Loading…' if not present in the entry; the
        screen's focus worker fills it in later via set_description().
        """
        vid = entry.get("id", "")
        self._current_id = vid
        self._last_entry = entry

        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))

        self.query_one("#video-title", Static).update(
            f"[bold white]{title}[/bold white]"
        )
        self.query_one("#video-channel", Static).update(
            f"📺 {channel}" if channel else ""
        )
        stats_parts = [p for p in [duration, views, age] if p]
        self.query_one("#video-stats", Static).update(
            "  [dim]·[/dim]  ".join(stats_parts)
        )

        desc = entry.get("description", "")
        if desc:
            self._set_description(desc)
        elif vid and not vid.startswith("__"):
            self.query_one("#video-desc-header", Static).update(
                "[dim]─── Description ──────────────────────────[/dim]"
            )
            self.query_one("#video-desc", Static).update("[dim]Loading…[/dim]")
        else:
            self.query_one("#video-desc-header", Static).update("")
            self.query_one("#video-desc", Static).update("")

        self._update_playlists(vid)

    def set_description(self, desc: str, *, vid: str | None = None) -> None:
        """Set the description text. If vid is given and doesn't match current, no-op."""
        if vid is not None and vid != self._current_id:
            return
        if desc:
            self._set_description(desc)

    def refresh_metadata(self, entry: dict) -> None:
        """Update channel/stats/description from a freshly enriched entry."""
        if entry.get("id") != self._current_id:
            return
        self._last_entry = entry

        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))

        self.query_one("#video-channel", Static).update(
            f"📺 {channel}" if channel else ""
        )
        stats_parts = [p for p in [duration, views, age] if p]
        self.query_one("#video-stats", Static).update(
            "  [dim]·[/dim]  ".join(stats_parts)
        )
        desc = entry.get("description", "")
        if desc:
            self._set_description(desc)

    # ── Thumbnail proxy ───────────────────────────────────────────────────────

    def set_thumbnail_video_id(self, vid: str) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_video_id(vid)

    def set_thumbnail_loading(self) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_loading()

    def set_thumbnail_placeholder(self) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_placeholder()

    def set_thumbnail_image(self, vid: str, path: "Path") -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_image_path(vid, path)

    def set_thumbnail_ansi(self, vid: str, ansi: str) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_ansi(vid, ansi)

    # ── Internal helpers ──────────────────────────────────────────────────────

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

    # ── Re-render hooks ───────────────────────────────────────────────────────

    def on_screen_resume(self, _: ScreenResume) -> None:
        if self._last_entry:
            self.post_message(self.RerenderRequested(self._last_entry))

    def on_resize(self, event: Resize) -> None:
        if self._last_entry:
            self.post_message(self.RerenderRequested(self._last_entry))
