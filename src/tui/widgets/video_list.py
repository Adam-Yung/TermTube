"""VideoListPanel — scrollable video list with live-streaming and lazy loading."""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

if TYPE_CHECKING:
    pass


# ── Constants ─────────────────────────────────────────────────────────────────

BATCH_SIZE = 20           # entries revealed per batch
PREFETCH_THRESHOLD = 5    # reveal next batch when cursor is within N of visible end

# ── Formatting helpers ────────────────────────────────────────────────────────

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
    """Convert yt-dlp YYYYMMDD string to relative age."""
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
    """Format a Unix timestamp as 'watched X ago'."""
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


# ── List item ─────────────────────────────────────────────────────────────────

class VideoListItem(ListItem):
    """A single video row in the list."""

    def __init__(self, entry: dict) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield Static(self._build_markup(), markup=True, shrink=True)

    def _build_markup(self) -> str:
        entry = self.entry
        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader") or entry.get("channel") or ""
        duration = _fmt_duration(entry.get("duration"))
        views = _fmt_views(entry.get("view_count"))
        age = _fmt_age(entry.get("upload_date"))
        watched = _fmt_watched(entry.get("_watched_at"))

        # Badge for local types / playlists
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

        # Truncate long titles
        if len(title) > 68:
            title = title[:65] + "…"

        line1 = f"[bold white]{title}[/bold white]{badge}"

        # Meta line — channel, duration, views, age
        meta_parts = []
        if channel:
            meta_parts.append(f"[#ff6666]{channel}[/#ff6666]")
        if duration:
            meta_parts.append(f"[dim]{duration}[/dim]")
        if views:
            meta_parts.append(f"[dim]{views}[/dim]")
        if age:
            meta_parts.append(f"[dim]{age}[/dim]")
        # Watched timestamp for history entries (shown distinctly)
        if watched:
            meta_parts.append(f"[#6699cc]{watched}[/#6699cc]")

        line2 = "  [dim]·[/dim]  ".join(meta_parts) if meta_parts else ""

        if line2:
            return f"{line1}\n{line2}"
        return line1


# ── Panel widget ──────────────────────────────────────────────────────────────

class VideoListPanel(Widget):
    """
    Left panel: scrollable list of videos with streaming + lazy loading.

    All streamed entries go into _buffer. Only BATCH_SIZE entries are shown
    in the ListView at a time. As the user scrolls near the bottom, the next
    batch is automatically revealed from the buffer.
    """

    # ── Messages ──────────────────────────────────────────────────────────────

    class Selected(Message):
        """Cursor moved to a new entry."""
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class Activated(Message):
        """User pressed Enter on an entry."""
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    class BatchRevealed(Message):
        """Fired when a new batch of videos is revealed in the list for lazy loading."""
        def __init__(self, entries: list[dict]) -> None:
            super().__init__()
            self.entries = entries

    # ── State ─────────────────────────────────────────────────────────────────

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer: list[dict] = []           # all entries received from the stream
        self._buffer_index: dict[str, int] = {} # video_id -> buffer position (O(1) lookup)
        self._visible: int = 0                  # how many are currently in the ListView
        self._loading = False
        self._initial_batch_posted: bool = False

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield Static("", id="list-header", markup=True)
        yield LoadingIndicator(id="list-loading-anim")
        yield ListView(id="list-view")
        yield Static("", id="list-loading", markup=True)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_entry(self) -> dict | None:
        lv = self.query_one("#list-view", ListView)
        if lv.index is None:
            return None
        try:
            child = lv.highlighted_child
            if isinstance(child, VideoListItem):
                return child.entry
        except Exception:
            pass
        return None

    def clear_and_set_loading(self) -> None:
        """Reset the list and show a beautiful loading state."""
        self._buffer = []
        self._buffer_index = {}
        self._visible = 0
        self._loading = True
        self._initial_batch_posted = False

        # Display our modern loader, hide list while empty
        self.query_one("#list-loading-anim", LoadingIndicator).display = True
        lv = self.query_one("#list-view", ListView)
        lv.display = False
        lv.clear()

        self.query_one("#list-breadcrumb", Static).update("")
        self.query_one("#list-header", Static).update("[dim]Loading…[/dim]")
        self.query_one("#list-loading", Static).update("")

    def set_breadcrumb(self, text: str) -> None:
        """Show a breadcrumb/subtitle (e.g., playlist name + back hint)."""
        self.query_one("#list-breadcrumb", Static).update(
            f"[dim]{text}[/dim]"
        )

    def set_empty_message(self, msg: str) -> None:
        """Show an informational message when there are no items."""
        self._loading = False
        self.query_one("#list-loading-anim", LoadingIndicator).display = False
        self.query_one("#list-view", ListView).display = True
        self.query_one("#list-header", Static).update(f"[dim]{msg}[/dim]")
        self.query_one("#list-loading", Static).update("")

    def set_error_message(self, msg: str) -> None:
        """Show an error state."""
        self._loading = False
        self.query_one("#list-loading-anim", LoadingIndicator).display = False
        self.query_one("#list-view", ListView).display = True
        self.query_one("#list-header", Static).update(f"[#ff4444]{msg}[/#ff4444]")
        self.query_one("#list-loading", Static).update("")

    def append_entry(self, entry: dict) -> None:
        """
        Buffer one entry from the stream. Immediately reveals it if:
          • still within the initial batch, OR
          • the cursor is already near the bottom of the visible list.
        """
        vid = entry.get("id", "")
        if vid:
            self._buffer_index[vid] = len(self._buffer)
        self._buffer.append(entry)
        n_total = len(self._buffer)

        lv = self.query_one("#list-view", ListView)

        # Reveal immediately if within the first batch
        if self._visible < BATCH_SIZE:
            self._reveal_entry(entry)
        elif lv.index is not None:
            # Leverage _reveal_next_batch so it properly emits our BatchRevealed message
            remaining = self._visible - 1 - lv.index
            if remaining <= PREFETCH_THRESHOLD:
                self._reveal_next_batch()

        # Update count header (shows total buffered, not just visible)
        self.query_one("#list-header", Static).update(
            f"[dim]{n_total} {'video' if n_total == 1 else 'videos'}[/dim]"
        )

    def _reveal_entry(self, entry: dict) -> None:
        """Add one entry to the ListView (makes it visible)."""
        # Switch loader off upon revealing first item
        anim = self.query_one("#list-loading-anim", LoadingIndicator)
        if anim.display:
            anim.display = False
            self.query_one("#list-view", ListView).display = True

        lv = self.query_one("#list-view", ListView)
        item = VideoListItem(entry)
        lv.append(item)
        self._visible += 1
        if self._visible == 1:
            lv.index = 0
        # Post BatchRevealed exactly once when the initial batch is fully visible
        if self._visible == BATCH_SIZE and not self._initial_batch_posted:
            self._initial_batch_posted = True
            self.post_message(self.BatchRevealed(list(self._buffer[:BATCH_SIZE])))

    def _reveal_next_batch(self) -> None:
        """Reveal the next BATCH_SIZE entries from the buffer, if any."""
        start = self._visible
        end = min(start + BATCH_SIZE, len(self._buffer))
        if start >= end:
            return
        
        revealed_entries = self._buffer[start:end]
        for entry in revealed_entries:
            self._reveal_entry(entry)
            
        # Update "more available" indicator
        remaining = len(self._buffer) - self._visible
        if remaining > 0 and self._loading:
            self.query_one("#list-loading", Static).update(
                f"[dim]  ↓ {remaining} more buffered — scroll to load[/dim]"
            )
            
        # Emit our new message so MainScreen knows to grab thumbnails for these!
        self.post_message(self.BatchRevealed(revealed_entries))

    def finish_loading(self) -> None:
        """Call when streaming is complete."""
        self._loading = False

        # Only hide the spinner here if no videos ever appeared (i.e. _reveal_entry
        # never ran, so the spinner is still visible). When at least one video was
        # revealed, _reveal_entry already hid the spinner.
        anim = self.query_one("#list-loading-anim", LoadingIndicator)
        if anim.display:
            anim.display = False
            self.query_one("#list-view", ListView).display = True

        n_total = len(self._buffer)
        n_hidden = n_total - self._visible

        if n_total == 0:
            self.query_one("#list-header", Static).update("[dim]No results[/dim]")
            self.query_one("#list-loading", Static).update("")
        else:
            self.query_one("#list-header", Static).update(
                f"[dim]{n_total} {'video' if n_total == 1 else 'videos'}[/dim]"
            )
            if n_hidden > 0:
                self.query_one("#list-loading", Static).update(
                    f"[dim]  ↓ scroll for {n_hidden} more[/dim]"
                )
            else:
                self.query_one("#list-loading", Static).update("")

        # For feeds with fewer than BATCH_SIZE entries, _reveal_entry never reaches
        # BATCH_SIZE so the initial BatchRevealed was never posted.  Emit it now so
        # enrichment/thumbnail pre-fetch still runs for these small feeds.
        if self._visible > 0 and not self._initial_batch_posted:
            self._initial_batch_posted = True
            self.post_message(self.BatchRevealed(list(self._buffer[:self._visible])))

    def _update_load_more_indicator(self) -> None:
        remaining = len(self._buffer) - self._visible
        if remaining > 0:
            self.query_one("#list-loading", Static).update(
                f"[dim]  ↓ scroll for {remaining} more[/dim]"
            )
        else:
            self.query_one("#list-loading", Static).update("")

    def update_entry_by_id(self, vid_id: str, entry: dict) -> None:
        """Update a buffered entry and refresh its visible list item, if any."""
        idx = self._buffer_index.get(vid_id)
        if idx is not None and idx < len(self._buffer):
            self._buffer[idx] = entry
        lv = self.query_one("#list-view", ListView)
        for item in lv.query(VideoListItem):
            if item.entry.get("id") == vid_id:
                item.entry = entry
                try:
                    item.query_one(Static).update(item._build_markup())
                except Exception:
                    pass
                break

    def cursor_down(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_down()

    def cursor_up(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_up()

    def cursor_to_top(self) -> None:
        if self._visible > 0:
            self.query_one("#list-view", ListView).index = 0

    def cursor_to_bottom(self) -> None:
        if self._visible > 0:
            self.query_one("#list-view", ListView).index = self._visible - 1

    # ── ListView events ───────────────────────────────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, VideoListItem):
            self.post_message(self.Selected(event.item.entry))

        # Lazy load: reveal next batch when cursor is within PREFETCH_THRESHOLD
        # of the end of the currently visible list.
        lv = self.query_one("#list-view", ListView)
        if lv.index is not None and self._visible < len(self._buffer):
            remaining_visible = self._visible - 1 - lv.index
            if remaining_visible <= PREFETCH_THRESHOLD:
                self._reveal_next_batch()
                self._update_load_more_indicator()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, VideoListItem):
            self.post_message(self.Activated(event.item.entry))

    # ── Focus passthrough ─────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.query_one("#list-view", ListView).focus()

