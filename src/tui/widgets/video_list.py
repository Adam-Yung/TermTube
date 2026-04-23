"""VideoListPanel — scrollable video list with live-streaming support."""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    pass


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
    """Left panel: scrollable list of videos with streaming support."""

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

    # ── State ─────────────────────────────────────────────────────────────────

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: list[dict] = []
        self._loading = False

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static("", id="list-breadcrumb", markup=True)
        yield Static("", id="list-header", markup=True)
        yield ListView(id="list-view")
        yield Static("", id="list-loading", markup=True)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_entry(self) -> dict | None:
        lv = self.query_one("#list-view", ListView)
        if lv.index is None:
            return None
        try:
            item = lv._nodes[lv.index]  # type: ignore[attr-defined]
            if isinstance(item, VideoListItem):
                return item.entry
        except (IndexError, AttributeError):
            pass
        return None

    def clear_and_set_loading(self) -> None:
        """Reset the list and show a loading state."""
        self._entries = []
        self._loading = True
        lv = self.query_one("#list-view", ListView)
        lv.clear()
        self.query_one("#list-breadcrumb", Static).update("")
        self.query_one("#list-header", Static).update("[dim]Loading…[/dim]")
        self.query_one("#list-loading", Static).update("[dim]  ● fetching…[/dim]")

    def set_breadcrumb(self, text: str) -> None:
        """Show a breadcrumb/subtitle (e.g., playlist name + back hint)."""
        self.query_one("#list-breadcrumb", Static).update(
            f"[dim]{text}[/dim]"
        )

    def set_empty_message(self, msg: str) -> None:
        """Show an informational message when there are no items."""
        self._loading = False
        self.query_one("#list-header", Static).update(f"[dim]{msg}[/dim]")
        self.query_one("#list-loading", Static).update("")

    def set_error_message(self, msg: str) -> None:
        """Show an error state."""
        self._loading = False
        self.query_one("#list-header", Static).update(f"[#ff4444]{msg}[/#ff4444]")
        self.query_one("#list-loading", Static).update("")

    def append_entry(self, entry: dict) -> None:
        """Add one entry to the list (called from thread via call_from_thread)."""
        self._entries.append(entry)
        lv = self.query_one("#list-view", ListView)
        item = VideoListItem(entry)
        lv.append(item)
        n = len(self._entries)
        self.query_one("#list-header", Static).update(
            f"[dim]{n} {'video' if n == 1 else 'videos'}[/dim]"
        )
        # Auto-select first item
        if n == 1:
            lv.index = 0

    def finish_loading(self) -> None:
        """Call when streaming is complete."""
        self._loading = False
        self.query_one("#list-loading", Static).update("")
        n = len(self._entries)
        if n == 0:
            self.query_one("#list-header", Static).update("[dim]No results[/dim]")
        else:
            self.query_one("#list-header", Static).update(
                f"[dim]{n} {'video' if n == 1 else 'videos'}[/dim]"
            )

    def cursor_down(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_down()

    def cursor_up(self) -> None:
        self.query_one("#list-view", ListView).action_cursor_up()

    def cursor_to_top(self) -> None:
        lv = self.query_one("#list-view", ListView)
        if lv._nodes:  # type: ignore[attr-defined]
            lv.index = 0

    def cursor_to_bottom(self) -> None:
        lv = self.query_one("#list-view", ListView)
        nodes = lv._nodes  # type: ignore[attr-defined]
        if nodes:
            lv.index = len(nodes) - 1

    # ── ListView events ───────────────────────────────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, VideoListItem):
            self.post_message(self.Selected(event.item.entry))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, VideoListItem):
            self.post_message(self.Activated(event.item.entry))

    # ── Focus passthrough ─────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.query_one("#list-view", ListView).focus()
