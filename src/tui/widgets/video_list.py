"""VideoListPanel — paged video list with fixed 20-entry pages.

Architecture:
- Holds all fetched pages in `_pages` dict (page_num → list of entries).
- Displays one page at a time via `load_page()`.
- PageIndicator at the bottom for ◀ / ▶ navigation.
- Page switches are only allowed when the target page is ready.
- Deduplication across all pages via `_seen_ids` set.
"""

from __future__ import annotations

import time as _time

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

from src import logger
from src.tui.widgets.page_indicator import PageIndicator

PAGE_SIZE = 20


def _fmt_duration(secs: int | float | None) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


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


def _fmt_watched(ts: float | None) -> str:
    if not ts:
        return ""
    delta = _time.time() - ts
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

    def _build_markup(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"

        theme_color = {
            "crimson": "#ff6666",
            "amber": "#e8820c",
            "ocean": "#0ea5e9",
            "midnight": "#a855f7",
        }.get(theme, "#ff6666")

        entry = self.entry
        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))
        watched = _fmt_watched(entry.get("_watched_at"))

        local_type = entry.get("_local_type", "")
        has_audio = entry.get("_has_audio", False)
        is_playlist = entry.get("_is_playlist", False)

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
    """Paged video list panel. Shows PAGE_SIZE entries at a time."""

    # ── Messages ──────────────────────────────────────────────────────────────

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

    # ── Init / compose / mount ────────────────────────────────────────────────

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pages: dict[int, list[dict]] = {}
        self._seen_ids: set[str] = set()
        self._current_page: int = 0
        self._max_visited_page: int = 0
        self._is_loading: bool = False
        self._prefetching: bool = False
        self._freshness: str = ""
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

    # ── Public properties ─────────────────────────────────────────────────────

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
    def max_visited_page(self) -> int:
        return self._max_visited_page

    @property
    def total_pages(self) -> int:
        return max(len(self._pages), 1)

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    # ── Page management ───────────────────────────────────────────────────────

    def add_page(self, page_num: int, entries: list[dict]) -> None:
        """Store a fetched page. Deduplicates by video ID across all pages."""
        deduped: list[dict] = []
        for entry in entries:
            vid = entry.get("id", "")
            if vid and vid in self._seen_ids:
                continue
            if vid:
                self._seen_ids.add(vid)
            deduped.append(entry)
        self._pages[page_num] = deduped
        self._update_page_indicator()
        logger.debug("video_list: added page %d (%d entries)", page_num, len(deduped))

    def load_page(self, page_num: int) -> bool:
        """Display a specific page. Returns False if page not available."""
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

        for entry in entries:
            item = VideoListItem(entry)
            vid = entry.get("id", "")
            if vid:
                self._items_by_id[vid] = item
            self._lv.append(item)

        if entries:
            self._lv.call_after_refresh(lambda: setattr(self._lv, "index", 0))

        self._lv.focus()
        self._update_page_indicator()
        return True

    def can_go_next(self) -> bool:
        """True if the next page exists and we're not loading."""
        if self._is_loading:
            return False
        return (self._current_page + 1) in self._pages

    def can_go_prev(self) -> bool:
        """True if previous page exists and we're not loading."""
        if self._is_loading:
            return False
        return self._current_page > 1 and (self._current_page - 1) in self._pages

    def page_entries(self, page_num: int) -> list[dict]:
        """Return entries for a given page number, or empty list."""
        return self._pages.get(page_num, [])

    def all_unseen_entries(self) -> list[dict]:
        """Return entries from pages the user hasn't visited, for stashing."""
        entries: list[dict] = []
        for pn in sorted(self._pages.keys()):
            if pn > self._max_visited_page:
                entries.extend(self._pages[pn])
        return entries

    # ── State management ──────────────────────────────────────────────────────

    def clear_and_set_loading(self) -> None:
        """Full reset: wipe all pages and show loading indicator."""
        self._pages.clear()
        self._seen_ids.clear()
        self._items_by_id.clear()
        self._current_page = 0
        self._max_visited_page = 0
        self._is_loading = True
        self._prefetching = False
        self._freshness = ""

        self._anim.display = True
        self._lv.display = False
        self._lv.clear()

        self._breadcrumb.update("")
        self._update_page_indicator()

    def set_loading(self, loading: bool) -> None:
        """Set the loading state (blocks page switching while True)."""
        self._is_loading = loading
        if loading:
            self._anim.display = True
            self._lv.display = False
        else:
            if self._anim.display:
                self._anim.display = False
                self._lv.display = True
        self._update_page_indicator()

    def finish_loading(self) -> None:
        """Mark loading as done."""
        self._is_loading = False
        if self._anim.display:
            self._anim.display = False
            self._lv.display = True
            self._lv.focus()
        self._update_page_indicator()

    def set_prefetching(self, active: bool) -> None:
        """Toggle the prefetch indicator on the page bar."""
        self._prefetching = active
        self._update_page_indicator()

    def show_next_page_loading(self) -> None:
        """Advance to the next page number and show the loading spinner."""
        self._current_page += 1
        self._is_loading = True
        self._items_by_id.clear()
        self._lv.clear()
        self._anim.display = True
        self._lv.display = False
        self._update_page_indicator()

    def set_freshness(self, text: str) -> None:
        self._freshness = text or ""

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

    # ── Entry management ──────────────────────────────────────────────────────

    def update_entry_by_id(self, vid_id: str, entry: dict) -> None:
        """In-place update of an already-visible list item (enrichment callback)."""
        for pn, page_entries in self._pages.items():
            for i, e in enumerate(page_entries):
                if e.get("id") == vid_id:
                    self._pages[pn][i] = entry
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

    def neighbor_id(self, vid_id: str, direction: int) -> str | None:
        """Return the ID of the entry at offset direction from vid_id on current page."""
        if self._current_page not in self._pages:
            return None
        entries = self._pages[self._current_page]
        for i, e in enumerate(entries):
            if e.get("id") == vid_id:
                target = i + direction
                if 0 <= target < len(entries):
                    return entries[target].get("id") or None
                return None
        return None

    # ── Cursor helpers (used by MainScreen) ───────────────────────────────────

    def cursor_index(self) -> int | None:
        return self._lv.index

    def cursor_down(self) -> None:
        self._lv.action_cursor_down()

    def cursor_up(self) -> None:
        self._lv.action_cursor_up()

    def cursor_to_top(self) -> None:
        if self._lv._nodes:
            self._lv.index = 0

    def cursor_to_bottom(self) -> None:
        count = len(self._lv._nodes)
        if count > 0:
            self._lv.index = count - 1

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _update_page_indicator(self) -> None:
        try:
            current = max(self._current_page, 1)
            total = max(self.total_pages, current)
            next_ready = (self._current_page + 1) in self._pages
            self._page_indicator.update_state(
                current=current,
                total=total,
                next_ready=next_ready,
                prefetching=self._prefetching,
            )
        except Exception:
            pass

    # ── Event handlers ────────────────────────────────────────────────────────

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
