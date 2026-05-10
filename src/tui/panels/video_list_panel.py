"""TermTube v2 — VideoListPanel (paged).

Left panel that shows a paged list of video entries.
Emits Selected and Activated messages when cursor moves or Enter is pressed.

Architecture:
- Holds one page of entries at a time (self._entries).
- PageIndicator at the bottom for ◀ / ▶ navigation.
- Prefetch flag is set by the screen when page N+1 is being fetched.
- O(1) cursor access via index.
- Deduplication within a feed's pages by video ID.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

from tui.components.video_card import VideoCard
from tui.components.page_indicator import PageIndicator
import history as _history
import library as _library


class VideoListPanel(Widget):

    DEFAULT_CSS = """
    VideoListPanel {
        width: 45%;
        border-right: solid $accent-darken-2;
    }
    #list-header {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $surface-darken-1;
    }
    #list-view {
        height: 1fr;
    }
    #list-loading {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-align: center;
    }
    PageIndicator {
        height: 1;
        dock: bottom;
    }
    """

    class Selected(Message):
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class Activated(Message):
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class PageChangeRequested(Message):
        def __init__(self, direction: int) -> None:
            super().__init__()
            self.direction = direction  # +1 or -1

    def __init__(self, theme: str = "crimson", **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme = theme
        self._entries: list[dict] = []
        self._id_to_index: dict[str, int] = {}
        self._current_page = 1
        self._total_pages = 1
        self._feed_key = ""
        self._loading = False
        self._video_dir = None
        self._audio_dir = None

    def compose(self) -> ComposeResult:
        yield Static("", id="list-header")
        yield LoadingIndicator(id="list-spinner")
        yield ListView(id="list-view")
        yield Static("", id="list-loading")
        yield PageIndicator(theme=self._theme, id="list-page-indicator")

    def on_mount(self) -> None:
        self.query_one("#list-spinner").display = False
        self.query_one("#list-loading").display = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_dirs(self, video_dir, audio_dir) -> None:
        self._video_dir = video_dir
        self._audio_dir = audio_dir

    def load_entries(
        self,
        entries: list[dict],
        *,
        feed_key: str = "",
        page: int = 1,
        total_pages: int = 1,
        loading: bool = False,
    ) -> None:
        """Replace current page contents with entries."""
        self._entries = entries
        self._id_to_index = {e.get("id", ""): i for i, e in enumerate(entries)}
        self._current_page = page
        self._total_pages = total_pages
        self._feed_key = feed_key
        self._loading = loading

        lv = self.query_one("#list-view", ListView)
        lv.clear()

        # Build watched and local library sets for badges
        watched_ids: set[str] = set()
        has_video_ids: set[str] = set()
        has_audio_ids: set[str] = set()
        try:
            watched_ids = {e.get("id") for e in _history.all_entries() if e.get("id")}
        except Exception:
            pass
        try:
            if self._video_dir or self._audio_dir:
                for lib_entry in _library.all_entries(
                    self._video_dir or "", self._audio_dir or ""
                ):
                    vid = lib_entry.get("id", "")
                    if lib_entry.get("_has_video"):
                        has_video_ids.add(vid)
                    if lib_entry.get("_has_audio"):
                        has_audio_ids.add(vid)
        except Exception:
            pass

        compact = (self.size.width or 80) < 80

        for idx, entry in enumerate(entries):
            vid = entry.get("id", "")
            card = VideoCard(
                entry,
                theme=self._theme,
                watched=(vid in watched_ids),
                has_video=(vid in has_video_ids),
                has_audio=(vid in has_audio_ids),
                compact=compact,
                id=f"card-{page}-{idx}",
            )
            lv.append(card)

        # Update page indicator
        pi = self.query_one("#list-page-indicator", PageIndicator)
        pi.current = page
        pi.total = total_pages

        self._refresh_header()
        self.query_one("#list-spinner").display = loading

        if lv._nodes:
            lv.index = 0
            lv.focus()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.query_one("#list-spinner").display = loading

    def set_prefetching(self, prefetching: bool) -> None:
        pi = self.query_one("#list-page-indicator", PageIndicator)
        pi.prefetching = prefetching

    def update_entry_by_id(self, video_id: str, entry: dict) -> None:
        idx = self._id_to_index.get(video_id)
        if idx is None:
            return
        self._entries[idx] = entry
        try:
            card_id = f"card-{self._current_page}-{idx}"
            card = self.query_one(f"#{card_id}", VideoCard)
            card.update_entry(entry)
        except Exception:
            pass

    def cursor_entry(self) -> dict | None:
        lv = self.query_one("#list-view", ListView)
        if lv.index is not None and 0 <= lv.index < len(self._entries):
            return self._entries[lv.index]
        return None

    def cursor_index(self) -> int:
        lv = self.query_one("#list-view", ListView)
        return lv.index or 0

    def neighbor_id(self, video_id: str, direction: int) -> str | None:
        idx = self._id_to_index.get(video_id)
        if idx is None:
            return None
        nidx = idx + direction
        if 0 <= nidx < len(self._entries):
            return self._entries[nidx].get("id")
        return None

    def cursor_down(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_down()

    def cursor_up(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_up()

    def cursor_to_top(self) -> None:
        lv = self.query_one("#list-view", ListView)
        lv.index = 0

    def cursor_to_bottom(self) -> None:
        lv = self.query_one("#list-view", ListView)
        if self._entries:
            lv.index = len(self._entries) - 1

    def set_header(self, text: str) -> None:
        try:
            self.query_one("#list-header", Static).update(text)
        except Exception:
            pass

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.query_one("#list-page-indicator", PageIndicator).set_theme(theme)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        entry = self.cursor_entry()
        if entry:
            self.post_message(self.Selected(entry))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        entry = self.cursor_entry()
        if entry:
            self.post_message(self.Selected(entry))

    def on_page_indicator_prev_page(self, _) -> None:
        self.post_message(self.PageChangeRequested(-1))

    def on_page_indicator_next_page(self, _) -> None:
        self.post_message(self.PageChangeRequested(+1))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_header(self) -> None:
        n = len(self._entries)
        self.set_header(f" {n} videos  ·  page {self._current_page}/{self._total_pages}")
