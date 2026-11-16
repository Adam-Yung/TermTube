"""Right panel: thumbnail, metadata and the action bar. A passive view; the screen drives it."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.events import Resize, ScreenResume
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from src import playlist
from src.entries import Entry
from src.tui.fmt import escape_markup, fmt_age, fmt_duration, fmt_subscribers, fmt_views
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.thumbnail_widget import ThumbnailWidget

_IDLE_HINT = "[dim]j/k move  ·  h/l page  ·  ⏎ actions  ·  v video  ·  a audio  ·  / search[/dim]"
_DESC_HEADER = "[dim]─── Description ──────────────────────────[/dim]"
_STATS_SEP = "  [dim]·[/dim]  "


class DetailPanel(Widget):
    class RerenderRequested(Message):
        """Posted on resize and screen resume so the screen re-renders the thumbnail."""

        def __init__(self, entry: Entry) -> None:
            super().__init__()
            self.entry = entry

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_id: str = ""
        self._last_entry: Entry | None = None
        self._resize_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="thumbnail-area"):
            yield ThumbnailWidget(id="thumbnail")
        with ScrollableContainer(id="video-info"):
            yield Static(_IDLE_HINT, id="video-title", markup=True)
            yield Static("", id="video-channel", markup=True)
            yield Static("", id="video-stats", markup=True)
            yield Static("", id="video-desc-header", markup=True)
            yield Static("", id="video-desc", markup=True)
            yield Static("", id="video-playlists", markup=True)
        yield ActionBar(id="action-bar")

    @property
    def action_bar(self) -> ActionBar:
        return self.query_one("#action-bar", ActionBar)

    @property
    def current_id(self) -> str:
        return self._current_id

    @property
    def last_entry(self) -> Entry | None:
        return self._last_entry

    def _text(self, selector: str, markup: str) -> None:
        self.query_one(selector, Static).update(markup)

    def clear(self) -> None:
        self._current_id = ""
        self._last_entry = None
        self.query_one("#thumbnail", ThumbnailWidget).set_placeholder()
        self._text("#video-title", _IDLE_HINT)
        for wid in ("#video-channel", "#video-stats", "#video-desc-header", "#video-desc", "#video-playlists"):
            self._text(wid, "")

    def update_basic(self, entry: Entry) -> None:
        """Paint title, channel and stats from the cached entry. Starts no workers.

        A missing description shows "Loading…" until the screen's focus worker fills it in.
        """
        vid = entry.get("id", "")
        self._current_id = vid
        self._last_entry = entry
        self._text("#video-title", f"[bold white]{escape_markup(entry.get('title') or 'Untitled')}[/bold white]")
        self._paint_channel_and_stats(entry)

        desc = entry.get("description", "")
        if desc:
            self._set_description(desc)
        elif vid and not vid.startswith("__"):
            self._text("#video-desc-header", _DESC_HEADER)
            self._text("#video-desc", "[dim]Loading…[/dim]")
        else:
            self._text("#video-desc-header", "")
            self._text("#video-desc", "")
        self._text("#video-playlists", "")

    def refresh_metadata(self, entry: Entry) -> None:
        """Repaint from a freshly enriched entry; ignored if the cursor has moved on."""
        if entry.get("id") != self._current_id:
            return
        self._last_entry = entry
        self._paint_channel_and_stats(entry)
        if entry.get("description"):
            self._set_description(entry["description"])

    def _paint_channel_and_stats(self, entry: Entry) -> None:
        channel = entry.get("uploader") or entry.get("channel") or ""
        # screen.channel is resolved on the screen, not on this panel.
        self._text("#video-channel", f"[@click=screen.channel]📺 {escape_markup(channel)}[/]" if channel else "")
        stats = [
            fmt_duration(entry.get("duration")),
            fmt_views(entry.get("view_count")),
            fmt_age(entry.get("upload_date")),
        ]
        self._text("#video-stats", _STATS_SEP.join(p for p in stats if p))

    def _set_description(self, desc: str) -> None:
        desc = desc.strip()
        if len(desc) > 500:
            desc = desc[:497] + "…"
        self._text("#video-desc-header", _DESC_HEADER)
        self._text("#video-desc", f"[dim]{escape_markup(desc)}[/dim]")

    def refresh_playlists(self, vid: str) -> None:
        names = playlist.video_playlists(vid) if vid and not vid.startswith("__") else []
        self._text("#video-playlists", "  ".join(f"[#6699cc]♪ {n}[/#6699cc]" for n in names))

    def thumbnail_cell_size(self) -> tuple[int, int]:
        """Cells available for the half-block fallback render."""
        try:
            size = self.query_one("#thumbnail").size
        except Exception:
            return 38, 20
        return size.width or max(30, (self.size.width or 80) - 4), size.height or 25

    def set_thumbnail_video_id(self, vid: str) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_video_id(vid)

    def set_thumbnail_loading(self) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_loading()

    def set_thumbnail_placeholder(self) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_placeholder()

    def set_thumbnail_image(self, vid: str, path: Path) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_image_path(vid, path)

    def set_thumbnail_ansi(self, vid: str, ansi: str) -> None:
        self.query_one("#thumbnail", ThumbnailWidget).set_ansi(vid, ansi)

    def on_screen_resume(self, _: ScreenResume) -> None:
        if self._last_entry:
            self.post_message(self.RerenderRequested(self._last_entry))

    def on_resize(self, event: Resize) -> None:
        if not self._last_entry:
            return
        if self._resize_timer:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(
            0.15, lambda: self.post_message(self.RerenderRequested(self._last_entry))
        )

    def set_channel_mode(self) -> None:
        """Subscriptions tab: hide the action bar; the panel shows channel info."""
        self.action_bar.display = False
        for wid in ("#video-stats", "#video-playlists"):
            self._text(wid, "")

    def set_video_mode(self) -> None:
        self.action_bar.display = True

    def update_channel_entry(self, entry: Entry) -> None:
        self._current_id = entry.get("id", "")
        self._last_entry = entry
        name = entry.get("channel") or entry.get("title") or entry.get("uploader") or "Channel"
        subs = fmt_subscribers(entry.get("subscriber_count"))
        vcnt = entry.get("video_count")
        url = entry.get("channel_url") or entry.get("uploader_url") or ""
        desc = entry.get("description") or ""
        stats = [f"{subs} subscribers" if subs else "", f"{vcnt} videos" if vcnt else ""]
        self._text("#video-title", f"[bold white]{escape_markup(name)}[/bold white]")
        self._text("#video-stats", "  ·  ".join(f"[dim]{p}[/dim]" for p in stats if p))
        self._text("#video-channel", f"[dim]{url[:60]}[/dim]" if url else "")
        self._text("#video-desc-header", "[dim]About[/dim]" if desc else "")
        self._text("#video-desc", escape_markup(desc[:1500]))
        self._text("#video-playlists", "")
