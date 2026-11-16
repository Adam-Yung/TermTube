"""Paged video list: fixed-size pages held in memory, one shown at a time."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

from src import logger
from src.tui.fmt import fmt_age, fmt_duration, fmt_subscribers, fmt_views
from src.tui.widgets.action_bar import THEME_COLORS
from src.tui.widgets.page_indicator import PageIndicator

PAGE_SIZE = 20
_MAX_PAGES_IN_MEMORY = 30


class _ItemClicked(Message):
    def __init__(self, entry: dict) -> None:
        super().__init__()
        self.entry = entry


class _ItemDoubleClicked(Message):
    def __init__(self, entry: dict) -> None:
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


class VideoListItem(ListItem):
    def __init__(self, entry: dict) -> None:
        super().__init__()
        self.entry = entry
        self._cached_markup: str = ""

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
        watched = _fmt_watched(entry.get("_watched_at"))

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
            line1 = f"[bold white]{ch_name}[/bold white] [{theme_color}]📺[/{theme_color}]"
            return f"{line1}\n{line2}" if line2 else line1

        if is_playlist:
            badge = " [#6b9eff]▶ PLAYLIST[/]"
        elif local_type == "video" and has_audio:
            badge = " [#6bff6b]↓ VIDEO+AUDIO[/]"
        elif local_type == "video":
            badge = " [#6bff6b]↓ VIDEO[/]"
        elif local_type == "audio":
            badge = " [#6b9eff]↓ AUDIO[/]"
        else:
            badge = ""

        if len(title) > 68:
            title = title[:65] + "…"

        line1 = f"[bold white]{title}[/bold white]{badge}"

        meta_parts = []
        if channel:
            meta_parts.append(f"[{theme_color}]{channel}[/{theme_color}]")
        if duration:
            meta_parts.append(f"[dim]{duration}[/dim]")
        if views:
            meta_parts.append(f"[dim]{views}[/dim]")
        if age:
            meta_parts.append(f"[dim]{age}[/dim]")
        if watched:
            meta_parts.append(f"[#6699cc]{watched}[/#6699cc]")

        line2 = "  [dim]·[/dim]  ".join(meta_parts) if meta_parts else ""
        return f"{line1}\n{line2}" if line2 else line1


class VideoListPanel(Widget):
    """Pages of ``PAGE_SIZE`` entries, deduplicated by id across pages."""

    class Selected(Message):
        """Cursor moved to a new item."""
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class Activated(Message):
        """User pressed Enter on an item."""
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class PageChangeRequested(Message):
        """User wants to switch page. direction: +1 or -1."""
        def __init__(self, direction: int) -> None:
            super().__init__()
            self.direction = direction

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pages: dict[int, list[dict]] = {}
        self._seen_ids: set[str] = set()
        self._current_page: int = 0
        self._max_visited_page: int = 0
        self._is_loading: bool = False
        self._items_by_id: dict[str, VideoListItem] = {}
        self._lv: ListView
        self._anim: LoadingIndicator
        self._breadcrumb: Static
        self._page_indicator: PageIndicator

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield LoadingIndicator(id="list-loading-anim")
        yield ListView(id="list-view")
        yield PageIndicator(id="list-page-indicator")

    def on_mount(self) -> None:
        self._lv = self.query_one("#list-view", ListView)
        self._anim = self.query_one("#list-loading-anim", LoadingIndicator)
        self._breadcrumb = self.query_one("#list-breadcrumb", Static)
        self._page_indicator = self.query_one("#list-page-indicator", PageIndicator)
        self._lv.focus()

    @property
    def selected_entry(self) -> dict | None:
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
    def current_page(self) -> int:
        return self._current_page

    @property
    def total_pages(self) -> int:
        return max(self._pages, default=1)

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    def add_page(self, page_num: int, entries: list[dict]) -> None:
        """Store a page, dropping ids already held. Evicts far-away pages beyond the cap."""
        deduped: list[dict] = []
        for entry in entries:
            vid = entry.get("id", "")
            if vid and vid in self._seen_ids:
                continue
            if vid:
                self._seen_ids.add(vid)
            deduped.append(entry)
        self._pages[page_num] = deduped
        if len(self._pages) > _MAX_PAGES_IN_MEMORY:
            keep_min = max(1, self._current_page - 2)
            keep_max = self._current_page + 2
            for pn in sorted(self._pages.keys()):
                if len(self._pages) <= _MAX_PAGES_IN_MEMORY:
                    break
                if pn < keep_min or pn > keep_max:
                    evicted = self._pages.pop(pn)
                    for e in evicted:
                        eid = e.get("id", "")
                        if eid:
                            self._seen_ids.discard(eid)
        self._update_page_indicator()
        logger.debug("video_list: added page %d (%d entries)", page_num, len(deduped))

    def load_page(self, page_num: int, *, cursor: str = "first") -> bool:
        """Display a page with the cursor on its first or last row. False if the page is not held."""
        if page_num not in self._pages:
            return False

        entries = self._pages[page_num]
        self._current_page = page_num
        if page_num > self._max_visited_page:
            self._max_visited_page = page_num

        self._is_loading = False
        self._items_by_id.clear()
        self._lv.clear()

        if self._anim.display:
            self._anim.display = False
            self._lv.display = True

        items_to_mount: list[VideoListItem] = []
        for entry in entries:
            item = VideoListItem(entry)
            vid = entry.get("id", "")
            if vid:
                self._items_by_id[vid] = item
            items_to_mount.append(item)
        self._lv.extend(items_to_mount)

        if entries:
            row = len(entries) - 1 if cursor == "last" else 0
            self._lv.call_after_refresh(lambda: setattr(self._lv, "index", row))

        self._lv.focus()
        self._update_page_indicator()
        return True

    def can_go_next(self) -> bool:
        if self._is_loading:
            return False
        return (self._current_page + 1) in self._pages

    def can_go_prev(self) -> bool:
        if self._is_loading:
            return False
        return self._current_page > 1 and (self._current_page - 1) in self._pages

    def all_unseen_entries(self) -> list[dict]:
        """Entries of pages the user never opened (the home stash)."""
        entries: list[dict] = []
        for pn in sorted(self._pages.keys()):
            if pn > self._max_visited_page:
                entries.extend(self._pages[pn])
        return entries

    def clear_and_set_loading(self) -> None:
        """Wipe all pages and show the loading indicator."""
        self._pages.clear()
        self._seen_ids.clear()
        self._items_by_id.clear()
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

    def update_entry_by_id(self, vid_id: str, entry: dict) -> None:
        """Replace an entry (held page and visible row) with its enriched version."""
        for pn, page_entries in self._pages.items():
            for i, e in enumerate(page_entries):
                if e.get("id") == vid_id:
                    self._pages[pn][i] = entry
                    break
            else:
                continue
            break

        item = self._items_by_id.get(vid_id)
        if item is None:
            return
        item.entry = entry
        try:
            item._cached_markup = item._build_markup()
            item.query_one(Static).update(item._cached_markup)
        except Exception:
            pass

    def add_entries(self, start_page: int, entries: list[dict]) -> None:
        """Add ``entries`` as consecutive PAGE_SIZE pages starting at ``start_page``."""
        for n, i in enumerate(range(0, len(entries), PAGE_SIZE)):
            self.add_page(start_page + n, entries[i:i + PAGE_SIZE])

    @property
    def seen_ids(self) -> set[str]:
        return set(self._seen_ids)

    def visited_entries(self) -> list[dict]:
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
        self._lv.index = 0

    def cursor_last(self) -> None:
        if len(self._lv):
            self._lv.index = len(self._lv) - 1

    def _update_page_indicator(self) -> None:
        try:
            current = max(self._current_page, 1)
            total = max(self.total_pages, current)
            next_ready = (self._current_page + 1) in self._pages
            self._page_indicator.update_state(
                current=current,
                total=total,
                next_ready=next_ready,
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
