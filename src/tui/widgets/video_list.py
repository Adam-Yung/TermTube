"""VideoListPanel — scrollable video list with live-streaming and lazy loading."""

from __future__ import annotations

import time as _time

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

from src import logger

BATCH_SIZE = 20
PREFETCH_THRESHOLD = 5


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
        # Cached markup — computed once in compose(), reused by update_entry_by_id.
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
    class Selected(Message):
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class Activated(Message):
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class BatchRevealed(Message):
        def __init__(self, entries: list[dict]) -> None:
            super().__init__()
            self.entries = entries

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer: list[dict] = []
        self._buffer_index: dict[str, int] = {}
        # O(1) widget index for in-place updates; populated in _reveal_entry.
        self._items_by_id: dict[str, VideoListItem] = {}
        self._visible: int = 0
        self._loading = False
        self._initial_batch_posted: bool = False
        # Freshness suffix shown in the list header (set by the screen).
        self._freshness: str = ""
        # Cached widget references — set in on_mount, avoids repeated DOM traversals.
        self._lv: ListView
        self._anim: LoadingIndicator
        self._header: Static
        self._breadcrumb: Static
        self._footer: Static

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield Static("", id="list-header", markup=True)
        yield LoadingIndicator(id="list-loading-anim")
        yield ListView(id="list-view")
        yield Static("", id="list-loading", markup=True)

    def on_mount(self) -> None:
        # Cache all frequently-accessed child widgets once to avoid repeated
        # DOM traversals during streaming (hundreds of calls per feed load).
        self._lv = self.query_one("#list-view", ListView)
        self._anim = self.query_one("#list-loading-anim", LoadingIndicator)
        self._header = self.query_one("#list-header", Static)
        self._breadcrumb = self.query_one("#list-breadcrumb", Static)
        self._footer = self.query_one("#list-loading", Static)
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

    def clear_and_set_loading(self) -> None:
        self._buffer = []
        self._buffer_index = {}
        self._items_by_id = {}
        self._visible = 0
        self._loading = True
        self._initial_batch_posted = False
        self._freshness = ""

        self._anim.display = True
        self._lv.display = False
        self._lv.clear()

        self._breadcrumb.update("")
        self._header.update("[dim]Loading…[/dim]")
        self._footer.update("")

    def set_freshness(self, text: str) -> None:
        """Set the freshness suffix shown in the list header (e.g. 'updated 4m ago · R to refresh')."""
        self._freshness = text or ""
        self._render_header()

    def _render_header(self) -> None:
        n_total = len(self._buffer)
        if n_total == 0:
            return
        base = f"{n_total} {'video' if n_total == 1 else 'videos'}"
        if self._freshness:
            self._header.update(f"[dim]{base}  ·  {self._freshness}[/dim]")
        else:
            self._header.update(f"[dim]{base}[/dim]")

    def set_breadcrumb(self, text: str) -> None:
        self._breadcrumb.update(f"[dim]{text}[/dim]")

    def set_empty_message(self, msg: str) -> None:
        self._loading = False
        self._anim.display = False
        self._lv.display = True
        self._header.update(f"[dim]{msg}[/dim]")
        self._footer.update("")

    def set_error_message(self, msg: str) -> None:
        self._loading = False
        self._anim.display = False
        self._lv.display = True
        self._header.update(f"[#ff4444]{msg}[/#ff4444]")
        self._footer.update("")

    def append_entry(self, entry: dict) -> None:
        vid = entry.get("id", "")
        if vid:
            self._buffer_index[vid] = len(self._buffer)
        self._buffer.append(entry)
        n_total = len(self._buffer)

        if self._visible < BATCH_SIZE:
            self._reveal_entry(entry)
        elif self._lv.index is not None:
            remaining = self._visible - 1 - self._lv.index
            if remaining <= PREFETCH_THRESHOLD:
                self._reveal_next_batch()

        self._render_header()

    def _reveal_entry(self, entry: dict) -> None:
        if self._anim.display:
            self._anim.display = False
            self._lv.display = True
            # Reclaim focus from the loading indicator transition; Textual may
            # have drifted focus to the Tabs widget while the animation was up.
            self._lv.focus()

        item = VideoListItem(entry)
        vid = entry.get("id", "")
        if vid:
            self._items_by_id[vid] = item
        self._lv.append(item)
        self._visible += 1
        if self._visible == 1:
            self._lv.index = 0
        if self._visible == BATCH_SIZE and not self._initial_batch_posted:
            self._initial_batch_posted = True
            self.post_message(self.BatchRevealed(list(self._buffer[:BATCH_SIZE])))

    def _reveal_next_batch(self) -> None:
        start = self._visible
        end = min(start + BATCH_SIZE, len(self._buffer))
        if start >= end:
            return

        revealed_entries = self._buffer[start:end]
        for entry in revealed_entries:
            self._reveal_entry(entry)

        # Reassert focus on the ListView after appending items — Textual can
        # drift focus to the Tabs widget during rapid DOM mutations, which
        # causes spurious TabActivated events that trigger view reloads.
        self._lv.focus()

        remaining = len(self._buffer) - self._visible
        if remaining > 0 and self._loading:
            self._footer.update(
                f"[dim]  ↓ {remaining} more buffered — scroll to load[/dim]"
            )

        logger.debug("video_list: revealed batch %d..%d (visible=%d, buffer=%d)",
                     start, end - 1, self._visible, len(self._buffer))
        self.post_message(self.BatchRevealed(revealed_entries))

    def finish_loading(self) -> None:
        self._loading = False
        if self._anim.display:
            self._anim.display = False
            self._lv.display = True

        n_total = len(self._buffer)
        n_hidden = n_total - self._visible

        if n_total == 0:
            self._header.update("[dim]No results[/dim]")
            self._footer.update("")
        else:
            self._render_header()
            if n_hidden > 0:
                self._footer.update(f"[dim]  ↓ scroll for {n_hidden} more[/dim]")
            else:
                self._footer.update("")

        if self._visible > 0 and not self._initial_batch_posted:
            self._initial_batch_posted = True
            self.post_message(self.BatchRevealed(list(self._buffer[: self._visible])))

    def _update_load_more_indicator(self) -> None:
        remaining = len(self._buffer) - self._visible
        if remaining > 0:
            self._footer.update(
                f"[dim]  ↓ scroll for {remaining} more[/dim]"
            )
        else:
            self._footer.update("")

    def update_entry_by_id(self, vid_id: str, entry: dict) -> None:
        idx = self._buffer_index.get(vid_id)
        if idx is not None and idx < len(self._buffer):
            self._buffer[idx] = entry
        item = self._items_by_id.get(vid_id)
        if item is None:
            return
        item.entry = entry
        try:
            item._cached_markup = item._build_markup()
            item.query_one(Static).update(item._cached_markup)
        except Exception:
            pass

    # ── Cursor neighbour lookup (for prefetch) ────────────────────────────────

    def neighbor_id(self, vid_id: str, direction: int) -> str | None:
        """Return the buffer ID at offset (direction = +1 or -1) from vid_id, or None."""
        idx = self._buffer_index.get(vid_id)
        if idx is None:
            return None
        target = idx + direction
        if 0 <= target < len(self._buffer):
            return self._buffer[target].get("id") or None
        return None

    def cursor_index(self) -> int | None:
        """Return the currently-highlighted ListView index, or None."""
        return self._lv.index

    def cursor_down(self) -> None:
        self._lv.action_cursor_down()

    def cursor_up(self) -> None:
        self._lv.action_cursor_up()

    def cursor_to_top(self) -> None:
        if self._visible > 0:
            self._lv.index = 0

    def cursor_to_bottom(self) -> None:
        if self._visible > 0:
            self._lv.index = self._visible - 1

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, VideoListItem):
            self.post_message(self.Selected(event.item.entry))

        if self._lv.index is not None and self._visible < len(self._buffer):
            remaining_visible = self._visible - 1 - self._lv.index
            if remaining_visible <= PREFETCH_THRESHOLD:
                self._reveal_next_batch()
                self._update_load_more_indicator()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, VideoListItem):
            self.post_message(self.Activated(event.item.entry))
