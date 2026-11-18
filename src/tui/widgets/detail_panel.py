"""Right panel: thumbnail, metadata and the action bar. A passive view; the screen drives it."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.events import Resize, ScreenResume
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from src import library, playlist
from src.entries import Entry
from src.tui.fmt import escape_markup, fmt_age, fmt_duration, fmt_size, fmt_subscribers, fmt_views
from src.tui.layout import MAX_THUMB_ROWS, MIN_INFO_ROWS, MIN_THUMB_ROWS
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
            yield Static("", id="video-file", markup=True)
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
        for wid in ("#video-channel", "#video-stats", "#video-file", "#video-desc-header", "#video-desc",
                    "#video-playlists"):
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
        self._text("#video-file", self._file_line(entry))

    def _file_line(self, entry: Entry) -> str:
        """For a Library row: where the file lives (relative to its download folder) and its total size."""
        if entry.get("_missing_file"):
            return "[#ff6b6b]⚠ file missing[/]"
        path = entry.get("_local_path")
        if not path:
            return ""
        config = self.app.config
        shown = path
        for root in (config.video_dir, config.audio_dir):
            try:
                shown = str(Path(path).relative_to(root))
                break
            except ValueError:
                continue
        size = fmt_size(library.total_size(entry))
        return f"[dim]📁 {escape_markup(shown)}{_STATS_SEP + size if size else ''}[/dim]"

    def _set_description(self, desc: str) -> None:
        desc = desc.strip()
        if len(desc) > 500:
            desc = desc[:497] + "…"
        self._text("#video-desc-header", _DESC_HEADER)
        self._text("#video-desc", f"[dim]{escape_markup(desc)}[/dim]")

    def refresh_playlists(self, vid: str) -> None:
        names = playlist.video_playlists(vid) if vid and not vid.startswith("__") else []
        listed = ", ".join(escape_markup(n) for n in names)
        self._text("#video-playlists", f"[#6699cc]♪ In playlists: {listed}[/#6699cc]" if names else "")

    def thumbnail_cell_size(self) -> tuple[int, int]:
        """Cells available for the half-block fallback render."""
        try:
            size = self.query_one("#thumbnail").size
        except Exception:
            return 38, 20
        return size.width or max(30, (self.size.width or 80) - 4), size.height or 25

    def _thumbnail(self) -> ThumbnailWidget | None:
        """The thumbnail widget, or None once this panel is torn down (its screen was popped or the app is quitting)."""
        try:
            return self.query_one("#thumbnail", ThumbnailWidget)
        except NoMatches:
            return None

    def set_thumbnail_video_id(self, vid: str) -> None:
        if thumb := self._thumbnail():
            thumb.set_video_id(vid)

    def set_thumbnail_loading(self) -> None:
        if thumb := self._thumbnail():
            thumb.set_loading()

    def set_thumbnail_placeholder(self) -> None:
        if thumb := self._thumbnail():
            thumb.set_placeholder()

    def set_thumbnail_image(self, vid: str, path: Path) -> None:
        if thumb := self._thumbnail():
            thumb.set_image_path(vid, path)

    def set_thumbnail_ansi(self, vid: str, ansi: str) -> None:
        if thumb := self._thumbnail():
            thumb.set_ansi(vid, ansi)

    def on_screen_resume(self, _: ScreenResume) -> None:
        if self._last_entry:
            self.post_message(self.RerenderRequested(self._last_entry))

    def fit(self) -> None:
        """Split the height: video info first, then the Actions panel; the thumbnail gets the rest, hidden if short."""
        bar = self.action_bar
        bar_rows = int(bar.styles.height.value) + bar.styles.margin.height if bar.display and bar.styles.height else 0
        area = self.query_one("#thumbnail-area")
        rows = min(MAX_THUMB_ROWS, self.size.height // 2, self.size.height - bar_rows - MIN_INFO_ROWS)
        area.display = rows >= MIN_THUMB_ROWS
        if area.display:
            area.styles.height = rows

    def on_action_bar_height_changed(self) -> None:
        self.fit()

    def on_resize(self, event: Resize) -> None:
        self.action_bar.render_actions()
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
        self.fit()
        for wid in ("#video-stats", "#video-file", "#video-playlists"):
            self._text(wid, "")

    def set_video_mode(self) -> None:
        self.action_bar.display = True
        self.fit()

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
