"""Paged video list: fixed-size pages held in memory, one shown at a time."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

from src import fuzzy, logger
from src.config import DEFAULT_ROWS_PER_PAGE
from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup
from src.tui.widgets.list_cursor import ListCursorMixin
from src.tui.widgets.list_filter import FilterBar, ListFilterMixin, paginate
from src.tui.widgets.list_footer import ListFooterMixin
from src.tui.widgets.page_indicator import PageIndicator
from src.tui.widgets.video_rows import HeaderListItem, VideoListItem

_MAX_PAGES_IN_MEMORY = 30
_MAX_MESSAGE = 400  # a raw exception text can be a whole page of HTML


class VideoListPanel(ListCursorMixin, ListFilterMixin, ListFooterMixin, Widget):
    """Pages of ``page_size`` entries (``rows_per_page``, latched at each list load), deduplicated by id across pages.

    ``_pages`` always holds every loaded entry. While a filter is active the list shows ``_filtered_pages``
    (the ranked matches, re-paged) instead; paging, the indicator and the cursor all follow the shown pages.
    """

    class Selected(Message):
        """Cursor moved to a new item."""
        def __init__(self, entry: Entry) -> None:
            super().__init__()
            self.entry = entry

    class Activated(Message):
        """User pressed Enter on an item."""
        def __init__(self, entry: Entry) -> None:
            super().__init__()
            self.entry = entry

    class PageChangeRequested(Message):
        """User wants to switch page. direction: +1 or -1."""
        def __init__(self, direction: int) -> None:
            super().__init__()
            self.direction = direction

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pages: dict[int, list[Entry]] = {}
        self._page_size = DEFAULT_ROWS_PER_PAGE
        self._seen_ids: set[str] = set()
        self._current_page: int = 0
        self._max_visited_page: int = 0
        self._is_loading: bool = False
        self._items_by_id: dict[str, VideoListItem] = {}
        self._marked: set[str] = set()
        self._playing_id: str | None = None
        self._filter: str = ""
        self._matcher: Callable[[list[Entry], str], list[Entry]] = fuzzy.rank
        self._filtered_pages: dict[int, list[Entry]] = {}
        self._anchor_page: int = 1
        self._group_by: Callable[[Entry], str] | None = None
        self._show_count: bool = False
        self._progress: str = ""
        self._notice: str = ""
        self._hidden = 0
        self._played_shown = False
        self._lv: ListView
        self._filter_bar: FilterBar
        self._anim: LoadingIndicator
        self._breadcrumb: Static
        self._message: Static
        self._page_indicator: PageIndicator

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield LoadingIndicator(id="list-loading-anim")
        yield Static("", id="list-message", markup=True)
        yield ListView(id="list-view")
        yield FilterBar(placeholder=text("video_list.filter_placeholder"), id="list-filter")
        yield PageIndicator(id="list-page-indicator")

    def on_mount(self) -> None:
        self._lv = self.query_one("#list-view", ListView)
        self._anim = self.query_one("#list-loading-anim", LoadingIndicator)
        self._breadcrumb = self.query_one("#list-breadcrumb", Static)
        self._message = self.query_one("#list-message", Static)
        self._filter_bar = self.query_one("#list-filter", FilterBar)
        self._page_indicator = self.query_one("#list-page-indicator", PageIndicator)
        self._lv.focus()

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def total_pages(self) -> int:
        """Pages of what is shown (the filtered set while filtering)."""
        return max(self._view_pages(), default=1)

    @property
    def next_page_number(self) -> int:
        """The page number a fetched extension starts at: after the last page of the full set."""
        return max(self._pages, default=0) + 1

    @property
    def loaded_count(self) -> int:
        """Entries held in the full set (not the filtered one)."""
        return sum(len(p) for p in self._pages.values())

    def _view_pages(self) -> dict[int, list[Entry]]:
        return self._filtered_pages if self._filter else self._pages

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    def add_page(self, page_num: int, entries: list[Entry], *, evict: bool = True) -> None:
        """Store a page, dropping ids already held. Evicts far-away pages beyond the cap unless ``evict`` is off."""
        deduped: list[Entry] = []
        for entry in entries:
            vid = entry.get("id", "")
            if vid and vid in self._seen_ids:
                continue
            if vid:
                self._seen_ids.add(vid)
            deduped.append(entry)
        self._pages[page_num] = deduped
        if evict:
            self._evict_far_pages()
        if self._filter:
            self._rebuild_filtered()
        self._update_page_indicator()
        logger.debug("video_list: added page %d (%d entries)", page_num, len(deduped))

    def _evict_far_pages(self) -> None:
        """Over the cap, drop pages more than two away from the one in view, forgetting their ids."""
        if len(self._pages) <= _MAX_PAGES_IN_MEMORY:
            return
        anchor = self._anchor_page if self._filter else self._current_page
        keep_min = max(1, anchor - 2)
        keep_max = anchor + 2
        far = [pn for pn in sorted(self._pages) if pn < keep_min or pn > keep_max]
        for pn in far[: len(self._pages) - _MAX_PAGES_IN_MEMORY]:
            self._seen_ids.difference_update(e.get("id", "") for e in self._pages.pop(pn) if e.get("id", ""))

    def load_page(
        self, page_num: int, *, cursor: str = "first", focus_id: str | None = None, focus: bool = True
    ) -> bool:
        """Show a page with the cursor on `focus_id`, else its first or last row. False if the page is not held.

        `focus=False` keeps keyboard focus where it is (the filter bar while typing).
        """
        entries = self._view_pages().get(page_num)
        if entries is None:
            return False

        self._current_page = page_num
        if not self._filter and page_num > self._max_visited_page:
            self._max_visited_page = page_num

        self._is_loading = False
        self._message.display = False
        self._lv.display = True
        rows = self._render_rows(entries)

        if self._anim.display:
            self._anim.display = False
            self._lv.display = True

        if entries:
            row = rows[-1] if cursor == "last" else rows[0]
            ids = [e.get("id") for e in entries]
            if focus_id is not None and focus_id in ids:
                row = rows[ids.index(focus_id)]
            self._lv.call_after_refresh(lambda: setattr(self._lv, "index", row))

        if focus:
            self._lv.focus()
        self._update_page_indicator()
        logger.stage("first rows")
        return True

    def _render_rows(self, entries: list[Entry]) -> list[int]:
        """Mount the rows (with day headers when grouped and not filtering). Returns each entry's list index."""
        self._items_by_id.clear()
        self._lv.clear()
        group = None if self._filter else self._group_by
        items: list[ListItem] = []
        rows: list[int] = []
        last_label: str | None = None
        for entry in entries:
            if group is not None:
                label = group(entry)
                if label != last_label:
                    items.append(HeaderListItem(label))
                    last_label = label
            vid = entry.get("id", "")
            item = VideoListItem(entry, marked=vid in self._marked, playing=bool(vid) and vid == self._playing_id)
            if vid:
                self._items_by_id[vid] = item
            rows.append(len(items))
            items.append(item)
        self._lv.extend(items)
        return rows

    def can_go_next(self) -> bool:
        if self._is_loading:
            return False
        return (self._current_page + 1) in self._view_pages()

    def can_go_prev(self) -> bool:
        if self._is_loading:
            return False
        return self._current_page > 1 and (self._current_page - 1) in self._view_pages()

    def all_unseen_entries(self) -> list[Entry]:
        """Entries of pages the user never opened (the home stash)."""
        entries: list[Entry] = []
        for pn in sorted(self._pages.keys()):
            if pn > self._max_visited_page:
                entries.extend(self._pages[pn])
        return entries

    def clear_and_set_loading(self) -> None:
        """Wipe all pages and show the loading indicator. Picks up a changed ``rows_per_page``."""
        self._page_size = self.app.config.rows_per_page
        self._pages.clear()
        self._seen_ids.clear()
        self._items_by_id.clear()
        self._marked.clear()
        self._group_by = None
        self._show_count = False
        self._progress = ""
        self._notice = ""
        self._hidden = 0
        self._played_shown = False
        self._reset_filter()
        self._current_page = 0
        self._max_visited_page = 0
        self._is_loading = True

        self._anim.display = True
        self._message.display = False
        self._lv.display = False
        self._lv.clear()

        self._breadcrumb.update("")
        self._update_page_indicator()

    def finish_loading(self) -> None:
        self._is_loading = False
        if self._anim.display:
            self._anim.display = False
            self._lv.display = True
            self._lv.focus()
        self._update_page_indicator()

    def show_next_page_loading(self) -> None:
        """Reserve the next page number and show the spinner until ``add_entries``/``load_page``."""
        self._current_page += 1
        self._is_loading = True
        self._items_by_id.clear()
        self._lv.clear()
        self._anim.display = True
        self._message.display = False
        self._lv.display = False
        self._update_page_indicator()

    def set_breadcrumb(self, text: str) -> None:
        self._breadcrumb.update(f"[dim]{escape_markup(text)}[/dim]")

    def _show_message(self, markup: str) -> None:
        """Replace the list with a wrapping message (empty list, failed load): the one-line breadcrumb would cut it."""
        self._is_loading = False
        self._anim.display = False
        self._lv.display = False
        self._message.update(markup)
        self._message.display = True

    def set_empty_message(self, msg: str) -> None:
        self._show_message(f"[dim]{escape_markup(msg)}[/dim]")

    def set_error_message(self, msg: str) -> None:
        self._show_message(f"[#ff4444]{escape_markup(msg[:_MAX_MESSAGE])}[/#ff4444]")

    def update_entry_by_id(self, vid_id: str, entry: Entry) -> None:
        """Replace an entry (held page and visible row) with its enriched version."""
        self._replace_held(vid_id, entry)
        if self._filter:
            self._rebuild_filtered()

        item = self._items_by_id.get(vid_id)
        if item is None:
            return
        item.entry = entry
        item.refresh_markup()

    def _replace_held(self, vid_id: str, entry: Entry) -> None:
        for page_entries in self._pages.values():
            for i, held in enumerate(page_entries):
                if held.get("id") == vid_id:
                    page_entries[i] = entry
                    return

    def add_entries(self, start_page: int, entries: list[Entry], *, evict: bool = True) -> None:
        """Add ``entries`` as consecutive ``page_size`` pages starting at ``start_page``."""
        size = self._page_size
        for n, i in enumerate(range(0, len(entries), size)):
            self.add_page(start_page + n, entries[i:i + size], evict=evict)

    def append_pages(self, entries: list[Entry], show: bool) -> None:
        """Add a fetched extension after the full set; with ``show`` land on its first page."""
        first = self.next_page_number
        self.add_entries(first, entries)
        if show and not self.load_page(first):
            self.finish_loading()

    @property
    def seen_ids(self) -> set[str]:
        return set(self._seen_ids)

    def visited_entries(self) -> list[Entry]:
        """Entries of every held page, in page order."""
        return [e for pn in sorted(self._pages) for e in self._pages[pn]]

    def set_playing(self, vid: str | None) -> None:
        """Badge this id as now playing from the next render on."""
        self._playing_id = vid

    def set_view_options(self, *, group_by: Callable[[Entry], str] | None = None, show_count: bool = False) -> None:
        """Day headers (`group_by` returns a row's label) and the footer item count. Reset on every view change."""
        self._group_by = group_by
        self._show_count = show_count
        self._update_page_indicator()

    def replace_entries(self, entries: list[Entry], *, focus_id: str | None = None) -> None:
        """Swap the full entry set (after a removal or undo), keeping the filter, marks and, if possible, the page."""
        self._pages = paginate(entries, self._page_size)
        self._seen_ids = {e["id"] for e in entries if e.get("id")}
        self._marked &= self._seen_ids
        if self._filter:
            self._rebuild_filtered()
        view = self._view_pages()
        if not view:
            self._current_page = 1
            self._render_rows([])
            self._update_page_indicator()
            return
        page = self._page_of(focus_id) or min(max(self._current_page, 1), max(view))
        self.load_page(page, focus_id=focus_id, focus=self.list_has_focus())

    def visible_ids(self) -> list[str]:
        """Ids of every row of the shown set (all pages), in order."""
        return [e["id"] for pn in sorted(self._view_pages()) for e in self._view_pages()[pn] if e.get("id")]

    def _page_of(self, vid: str | None) -> int | None:
        if vid is None:
            return None
        for pn, page_entries in self._view_pages().items():
            if any(e.get("id") == vid for e in page_entries):
                return pn
        return None
