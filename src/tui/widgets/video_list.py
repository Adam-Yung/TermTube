"""Paged video list: fixed-size pages held in memory, one shown at a time."""

from __future__ import annotations

import time
from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, ListItem, ListView, LoadingIndicator, Static

from src import fuzzy, logger
from src.config import DEFAULT_ROWS_PER_PAGE
from src.entries import Entry
from src.tui.fmt import escape_markup, fmt_age, fmt_clock, fmt_duration, fmt_subscribers, fmt_views
from src.tui.widgets.action_bar import THEME_COLORS
from src.tui.widgets.page_indicator import PageIndicator

_MAX_PAGES_IN_MEMORY = 30


_DL_BADGES = {
    "video": " [#6bff6b]⬇ video[/]",
    "audio": " [#6b9eff]⬇ audio[/]",
    "both": " [#6bff6b]⬇ both[/]",
    "": " [dim]☁[/dim]",
}


def _paginate(entries: list[Entry], size: int) -> dict[int, list[Entry]]:
    return {n + 1: entries[i:i + size] for n, i in enumerate(range(0, len(entries), size))}


class _ItemClicked(Message):
    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry


class _ItemDoubleClicked(Message):
    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry

def _fmt_watched(ts: float | None) -> str:
    if not ts:
        return ""
    delta = time.time() - ts
    if delta < 60:
        return "watched just now"
    if delta < 3600:
        return f"watched {int(delta / 60)}m ago"
    if delta < 86400:
        return f"watched {int(delta / 3600)}h ago"
    if delta < 86400 * 30:
        return f"watched {int(delta / 86400)}d ago"
    return f"watched {int(delta / (86400 * 30))}mo ago"


class HeaderListItem(ListItem):
    """A group label between rows (a day in History). Disabled, so the cursor never lands on it."""

    def __init__(self, label: str) -> None:
        super().__init__(disabled=True)
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(f"[bold #888888]{escape_markup(self._label)}[/bold #888888]", markup=True)


class FilterBar(Input):
    """One-line filter field at the foot of the list. Esc posts ``Cancelled``."""

    DEFAULT_CSS = """
    FilterBar, FilterBar:focus {
        display: none;
        dock: bottom;
        height: 1;
        margin-bottom: 1;
        padding: 0 1;
        border: none;
    }
    """
    BINDINGS = [Binding("escape", "cancel", show=False)]

    class Cancelled(Message):
        pass

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())


class VideoListItem(ListItem):
    def __init__(self, entry: Entry, *, marked: bool = False) -> None:
        super().__init__()
        self.entry = entry
        self.marked = marked
        self._cached_markup: str = ""

    def set_marked(self, marked: bool) -> None:
        self.marked = marked
        self.refresh_markup()

    def refresh_markup(self) -> None:
        self._cached_markup = self._build_markup()
        try:
            self.query_one(Static).update(self._cached_markup)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        self._cached_markup = self._build_markup()
        yield Static(self._cached_markup, markup=True, shrink=True)

    def on_click(self, event: Click) -> None:
        event.stop()
        event.prevent_default()
        self.post_message(_ItemClicked(self.entry))

    def on_double_click(self, event: Click) -> None:
        event.stop()
        event.prevent_default()
        if isinstance(self.parent, ListView):
            self.parent.index = self.parent.children.index(self)
        self.post_message(_ItemDoubleClicked(self.entry))

    def _build_markup(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"

        theme_color = THEME_COLORS.get(theme, "#ff6666")

        entry = self.entry
        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = fmt_duration(entry.get("duration"))
        views = fmt_views(entry.get("view_count"))
        age = fmt_age(entry.get("upload_date")) or entry.get("published_text", "")
        watched = _fmt_watched(entry.get("watched_at"))

        local_type = entry.get("_local_type", "")
        has_audio = entry.get("_has_audio", False)
        is_playlist = entry.get("_is_playlist", False)
        is_channel = entry.get("_is_channel", False)

        if is_channel:
            ch_name = entry.get("channel") or entry.get("title") or entry.get("uploader") or "Channel"
            if len(ch_name) > 50:
                ch_name = ch_name[:47] + "..."
            subs = fmt_subscribers(entry.get("subscriber_count"))
            vcnt = entry.get("video_count")
            parts = [f"{subs} subs" if subs else "", f"{vcnt} videos" if vcnt else ""]
            line2 = "  [dim]·[/dim]  ".join(f"[dim]{p}[/dim]" for p in parts if p)
            line1 = f"[bold white]{escape_markup(ch_name)}[/bold white] [{theme_color}]📺[/{theme_color}]"
            return f"{line1}\n{line2}" if line2 else line1

        if entry.get("_missing_file"):
            badge = " [#ff6b6b]⚠ file missing[/]"
        elif is_playlist:
            badge = " [#6b9eff]▶ PLAYLIST[/]"
        elif "_dl" in entry:
            badge = _DL_BADGES[entry["_dl"]]
        elif local_type == "video" and has_audio:
            badge = " [#6bff6b]↓ VIDEO+AUDIO[/]"
        elif local_type == "video":
            badge = " [#6bff6b]↓ VIDEO[/]"
        elif local_type == "audio":
            badge = " [#6b9eff]↓ AUDIO[/]"
        elif entry.get("_yt") or entry.get("source") == "yt":
            badge = " [#ff8c6b]YT[/]"
        else:
            badge = ""

        if len(title) > 68:
            title = title[:65] + "…"

        mark = f"[bold {theme_color}]●[/bold {theme_color}] " if self.marked else ""
        line1 = f"{mark}[bold white]{escape_markup(title)}[/bold white]{badge}"

        meta_parts = []
        if channel:
            meta_parts.append(f"[{theme_color}]{escape_markup(channel)}[/{theme_color}]")
        if duration:
            meta_parts.append(f"[dim]{duration}[/dim]")
        if views:
            meta_parts.append(f"[dim]{views}[/dim]")
        if age:
            meta_parts.append(f"[dim]{age}[/dim]")
        if watched:
            meta_parts.append(f"[#6699cc]{watched}[/#6699cc]")
        resume = entry.get("resume_s")
        if resume and entry.get("duration"):
            meta_parts.append(f"[#6bff6b]▶ {fmt_clock(resume)} / {duration}[/#6bff6b]")
        if (entry.get("plays") or 0) > 1:
            meta_parts.append(f"[dim]×{entry['plays']}[/dim]")

        line2 = "  [dim]·[/dim]  ".join(meta_parts) if meta_parts else ""
        return f"{line1}\n{line2}" if line2 else line1


class VideoListPanel(Widget):
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
        self._filter: str = ""
        self._matcher: Callable[[list[Entry], str], list[Entry]] = fuzzy.rank
        self._filtered_pages: dict[int, list[Entry]] = {}
        self._anchor_page: int = 1
        self._group_by: Callable[[Entry], str] | None = None
        self._show_count: bool = False
        self._lv: ListView
        self._filter_bar: FilterBar
        self._anim: LoadingIndicator
        self._breadcrumb: Static
        self._page_indicator: PageIndicator

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield LoadingIndicator(id="list-loading-anim")
        yield ListView(id="list-view")
        yield FilterBar(placeholder="Filter…  Enter keeps it, Esc clears", id="list-filter")
        yield PageIndicator(id="list-page-indicator")

    def on_mount(self) -> None:
        self._lv = self.query_one("#list-view", ListView)
        self._anim = self.query_one("#list-loading-anim", LoadingIndicator)
        self._breadcrumb = self.query_one("#list-breadcrumb", Static)
        self._filter_bar = self.query_one("#list-filter", FilterBar)
        self._page_indicator = self.query_one("#list-page-indicator", PageIndicator)
        self._lv.focus()

    @property
    def selected_entry(self) -> Entry | None:
        if self._lv.index is None:
            return None
        try:
            child = self._lv.highlighted_child
            if isinstance(child, VideoListItem):
                return child.entry
        except Exception:
            pass
        return None

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
    def filter_active(self) -> bool:
        return bool(self._filter)

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
        if evict and len(self._pages) > _MAX_PAGES_IN_MEMORY:
            anchor = self._anchor_page if self._filter else self._current_page
            keep_min = max(1, anchor - 2)
            keep_max = anchor + 2
            for pn in sorted(self._pages.keys()):
                if len(self._pages) <= _MAX_PAGES_IN_MEMORY:
                    break
                if pn < keep_min or pn > keep_max:
                    evicted = self._pages.pop(pn)
                    for e in evicted:
                        eid = e.get("id", "")
                        if eid:
                            self._seen_ids.discard(eid)
        if self._filter:
            self._rebuild_filtered()
        self._update_page_indicator()
        logger.debug("video_list: added page %d (%d entries)", page_num, len(deduped))

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
            item = VideoListItem(entry, marked=vid in self._marked)
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
        self._reset_filter()
        self._current_page = 0
        self._max_visited_page = 0
        self._is_loading = True

        self._anim.display = True
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
        self._lv.display = False
        self._update_page_indicator()

    def set_breadcrumb(self, text: str) -> None:
        self._breadcrumb.update(f"[dim]{text}[/dim]")

    def set_empty_message(self, msg: str) -> None:
        self._is_loading = False
        self._anim.display = False
        self._lv.display = True
        self._breadcrumb.update(f"[dim]{msg}[/dim]")

    def set_error_message(self, msg: str) -> None:
        self._is_loading = False
        self._anim.display = False
        self._lv.display = True
        self._breadcrumb.update(f"[#ff4444]{msg}[/#ff4444]")

    def update_entry_by_id(self, vid_id: str, entry: Entry) -> None:
        """Replace an entry (held page and visible row) with its enriched version."""
        for pn, page_entries in self._pages.items():
            for i, e in enumerate(page_entries):
                if e.get("id") == vid_id:
                    self._pages[pn][i] = entry
                    break
            else:
                continue
            break
        if self._filter:
            self._rebuild_filtered()

        item = self._items_by_id.get(vid_id)
        if item is None:
            return
        item.entry = entry
        item.refresh_markup()

    def add_entries(self, start_page: int, entries: list[Entry], *, evict: bool = True) -> None:
        """Add ``entries`` as consecutive ``page_size`` pages starting at ``start_page``."""
        size = self._page_size
        for n, i in enumerate(range(0, len(entries), size)):
            self.add_page(start_page + n, entries[i:i + size], evict=evict)

    @property
    def seen_ids(self) -> set[str]:
        return set(self._seen_ids)

    def visited_entries(self) -> list[Entry]:
        """Entries of every held page, in page order."""
        return [e for pn in sorted(self._pages) for e in self._pages[pn]]

    def focus_list(self) -> None:
        self._lv.focus()

    def list_has_focus(self) -> bool:
        return self.app.focused is self._lv

    def cursor_down(self) -> None:
        self._lv.action_cursor_down()

    def cursor_up(self) -> None:
        self._lv.action_cursor_up()

    def cursor_first(self) -> None:
        for i, child in enumerate(self._lv.children):
            if isinstance(child, VideoListItem):
                self._lv.index = i
                return

    def cursor_last(self) -> None:
        if len(self._lv):
            self._lv.index = len(self._lv) - 1

    def set_matcher(self, matcher: Callable[[list[Entry], str], list[Entry]] | None) -> None:
        """How the filter ranks entries for the view being loaded; None restores the plain free-text match."""
        self._matcher = matcher or fuzzy.rank

    def set_view_options(self, *, group_by: Callable[[Entry], str] | None = None, show_count: bool = False) -> None:
        """Day headers (`group_by` returns a row's label) and the footer item count. Reset on every view change."""
        self._group_by = group_by
        self._show_count = show_count
        self._update_page_indicator()

    def replace_entries(self, entries: list[Entry], *, focus_id: str | None = None) -> None:
        """Swap the full entry set (after a removal or undo), keeping the filter, marks and, if possible, the page."""
        self._pages = _paginate(entries, self._page_size)
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

    def open_filter(self) -> bool:
        """Show the filter bar and focus it. False when there is nothing loaded to filter."""
        if self._is_loading or not self._pages:
            return False
        self._filter_bar.display = True
        self._filter_bar.focus()
        return True

    def close_filter(self) -> None:
        """Drop the filter, hide the bar and return focus to the list, the cursor staying on the same video."""
        self._drop_filter()
        self._reset_filter()
        self._lv.focus()

    def _reset_filter(self) -> None:
        self._filter = ""
        self._filtered_pages = {}
        if hasattr(self, "_filter_bar"):
            self._filter_bar.value = ""
            self._filter_bar.display = False

    def _apply_filter(self, query: str) -> None:
        if not query:
            self._drop_filter()
            return
        if not self._filter:
            self._anchor_page = self._current_page
        self._filter = query
        self._rebuild_filtered()
        if self._filtered_pages:
            self.load_page(1, focus=False)
        else:
            self._current_page = 1
            self._render_rows([])
            self._update_page_indicator()

    def _drop_filter(self) -> None:
        if not self._filter:
            return
        selected = self.selected_entry
        sid = selected.get("id") if selected else None
        self._filter = ""
        self._filtered_pages = {}
        page = self._page_of(sid) or min(self._anchor_page, max(self._pages, default=1))
        self.load_page(max(page, 1), focus_id=sid, focus=False)

    def _rebuild_filtered(self) -> None:
        matched = self._matcher(self.visited_entries(), self._filter)
        self._filtered_pages = _paginate(matched, self._page_size)

    def toggle_mark(self, entry: Entry) -> None:
        vid = entry.get("id", "")
        if not vid:
            return
        marked = vid not in self._marked
        self._marked.add(vid) if marked else self._marked.discard(vid)
        item = self._items_by_id.get(vid)
        if item is not None:
            item.set_marked(marked)
        self._update_page_indicator()

    def mark_page(self) -> None:
        """Mark every row of the shown page; when all are marked already, unmark them."""
        ids = [e["id"] for e in self._view_pages().get(self._current_page, []) if e.get("id")]
        mark = not all(i in self._marked for i in ids)
        for vid in ids:
            self._marked.add(vid) if mark else self._marked.discard(vid)
            item = self._items_by_id.get(vid)
            if item is not None:
                item.set_marked(mark)
        self._update_page_indicator()

    def marked_entries(self) -> list[Entry]:
        """Marked rows of the full set (also those on other pages), in list order."""
        return [e for e in self.visited_entries() if e.get("id") in self._marked]

    def _status_note(self) -> str:
        shown = sum(len(p) for p in self._view_pages().values())
        total = sum(len(p) for p in self._pages.values())
        parts = []
        if self._filter:
            parts.append(f"{shown} of {total} match")
        elif self._show_count:
            parts.append(f"{total} videos")
        if self._marked:
            parts.append(f"{len(self._marked)} marked")
        return "  ·  ".join(parts)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        query = event.value.strip()
        if query != self._filter:
            self._apply_filter(query)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if not self._filter:
            self._filter_bar.display = False
        self._lv.focus()

    def on_filter_bar_cancelled(self, event: FilterBar.Cancelled) -> None:
        event.stop()
        self.close_filter()

    def _update_page_indicator(self) -> None:
        try:
            current = max(self._current_page, 1)
            total = max(self.total_pages, current)
            next_ready = (self._current_page + 1) in self._view_pages()
            self._page_indicator.update_state(
                current=current,
                total=total,
                next_ready=next_ready,
                note=self._status_note(),
            )
        except Exception:
            pass

    def on__item_clicked(self, msg: _ItemClicked) -> None:
        highlighted = self._lv.highlighted_child
        already_focused = (
            isinstance(highlighted, VideoListItem)
            and highlighted.entry.get("id") == msg.entry.get("id")
        )
        if already_focused:
            self.post_message(self.Activated(msg.entry))
        else:
            for i, child in enumerate(self._lv.children):
                if isinstance(child, VideoListItem) and child.entry.get("id") == msg.entry.get("id"):
                    self._lv.index = i
                    break

    def on__item_double_clicked(self, msg: _ItemDoubleClicked) -> None:
        self.post_message(self.Activated(msg.entry))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, VideoListItem):
            self.post_message(self.Selected(event.item.entry))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, VideoListItem):
            self.post_message(self.Activated(event.item.entry))

    def on_page_indicator_prev_page(self, event: PageIndicator.PrevPage) -> None:
        event.stop()
        if self.can_go_prev():
            self.post_message(self.PageChangeRequested(-1))

    def on_page_indicator_next_page(self, event: PageIndicator.NextPage) -> None:
        event.stop()
        if self.can_go_next():
            self.post_message(self.PageChangeRequested(+1))
