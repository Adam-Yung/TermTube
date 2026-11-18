"""The keymap: the only place keys are bound in code. Prose lives in docs/features/keybindings.md."""

from __future__ import annotations

from typing import NamedTuple

from textual.binding import Binding

from src.strings import text

LIST_NAV = [
    Binding("j", "cursor_down", show=False),
    Binding("k", "cursor_up", show=False),
    Binding("h,left", "page_prev", show=False),
    Binding("l,right", "page_next", show=False),
    Binding("g", "goto_start", show=False),
    Binding("G", "goto_end", show=False),
    Binding("H", "tab_prev", show=False),
    Binding("L", "tab_next", show=False),
    Binding("enter", "activate", show=False),
]

PLAYBACK = [
    Binding("v", "watch", show=False),
    Binding("V", "watch_quality", show=False),
    Binding("a", "audio", show=False),
    Binding("A", "audio_quality", show=False),
    Binding("e", "audio_enqueue", show=False),
    Binding(">", "audio_skip", show=False),
    Binding("Q", "audio_queue", show=False),
    Binding("space", "audio_pause", show=False),
    Binding("x", "audio_stop", show=False),
    Binding("left_square_bracket", "audio_seek(-5)", show=False),
    Binding("right_square_bracket", "audio_seek(5)", show=False),
    Binding("left_curly_bracket", "audio_seek(-10)", show=False),
    Binding("right_curly_bracket", "audio_seek(10)", show=False),
    *[Binding(str(n), f"audio_seek_pct({n * 10})", show=False) for n in range(10)],
]

ITEM_ACTIONS = [
    Binding("d", "download", show=False),
    Binding("c", "channel", show=False),
    Binding("y", "copy_url", show=False),
    Binding("p", "playlist", show=False),
    Binding("b", "browser", show=False),
]



class RowAction(NamedTuple):
    """An action on the highlighted row: in the Enter menu when it applies, in the Actions panel when ``bar`` is set."""

    action: str
    icon: str
    label: str
    bar: str | None


ROW_ACTIONS = [
    RowAction("watch", "▶", text("keymap.row_watch"), text("keymap.row_watch_bar")),
    RowAction("watch_quality", "▶·", text("keymap.row_watch_quality"), None),
    RowAction("audio", "♪", text("keymap.row_audio"), text("keymap.row_audio_bar")),
    RowAction("audio_quality", "♪·", text("keymap.row_audio_quality"), None),
    RowAction("audio_enqueue", "♪+", text("keymap.row_audio_enqueue"), None),
    RowAction("download", "↓", text("keymap.row_download"), text("keymap.row_download_bar")),
    RowAction("channel", "📺", text("keymap.row_channel"), text("keymap.row_channel_bar")),
    RowAction("copy_url", "⎘", text("keymap.row_copy_url"), text("keymap.row_copy_url_bar")),
    RowAction("playlist", "+", text("keymap.row_playlist"), text("keymap.row_playlist_bar")),
    RowAction("browser", "🌐", text("keymap.row_browser"), text("keymap.row_browser_bar")),
]


def key_of(action: str) -> str:
    """The key bound to an action, read from the bindings so the menu and the panel cannot drift from them.

    A screen's own binding wins where two lists bind a key to different actions (``P`` plays a playlist or a channel).
    """
    bound = (*PLAYBACK, *ITEM_ACTIONS, FILTER, *LIST_TOOLS, *HISTORY_KEYS, *PLAYLIST_TOOLS, *SEARCH_FILTERS,
             *HOME, *CHANNEL_PAGE)
    return next(b.key for b in bound if b.action == action)


FILTER = Binding("f", "filter", show=False)
RAIL = Binding("tab", "rail_toggle", show=False)

LIST_TOOLS = [
    Binding("m", "mark", show=False),
    Binding("M", "mark_page", show=False),
    Binding("D", "delete", show=False),
    Binding("u", "undo", show=False),
]

HISTORY_KEYS = [
    Binding("I", "history_import", show=False),
]

PLAYLIST_TOOLS = [
    Binding("n", "playlist_new", show=False),
    Binding("R", "playlist_rename", show=False),
    Binding("J", "playlist_move_down", show=False),
    Binding("K", "playlist_move_up", show=False),
    Binding("P", "playlist_play", show=False),
    Binding("S", "playlist_shuffle", show=False),
    Binding("E", "playlist_enqueue", show=False),
]

SEARCH = Binding("/", "search", "Search")
SEARCH_FILTERS = [
    Binding("s", "search_sort", show=False),
    Binding("t", "search_type", show=False),
]
GLOBAL = [
    Binding("comma", "settings", "Settings"),
    Binding("q", "quit_app", "Quit"),
    Binding("?", "help", "Help"),
]

CHANNEL_PAGE = [
    Binding("s", "sort", "Sort"),
    Binding("r", "reload", "Reload"),
    Binding("i", "info", "Info"),
    Binding("P", "play_all", show=False),
    Binding("E", "enqueue_all", show=False),
    Binding("S", "save_list", show=False),
    Binding("B", "bookmark", show=False),
]

HOME = [Binding("Z", "show_played", show=False)]

FOCUS_RECLAIM_KEYS = frozenset(
    {"j", "k", "h", "l", "up", "down", "left", "right", "enter", "g", "G", "H", "L"}
)


class PanelTool(NamedTuple):
    """A tool the Actions panel lists when its screen says it applies: one or more bound actions shown as one entry."""

    actions: tuple[str, ...]
    label: str


PANEL_TOOLS = [
    PanelTool(("filter",), text("keymap.tool_filter")),
    PanelTool(("mark",), text("keymap.tool_mark")),
    PanelTool(("delete",), text("keymap.tool_delete")),
    PanelTool(("undo",), text("keymap.tool_undo")),
    PanelTool(("history_import",), text("keymap.tool_history_import")),
    PanelTool(("search_sort",), text("keymap.tool_search_sort")),
    PanelTool(("search_type",), text("keymap.tool_search_type")),
    PanelTool(("show_played",), text("keymap.tool_show_played")),
    PanelTool(("playlist_new",), text("keymap.tool_playlist_new")),
    PanelTool(("playlist_rename",), text("keymap.tool_playlist_rename")),
    PanelTool(("playlist_move_down", "playlist_move_up"), text("keymap.tool_playlist_move")),
    PanelTool(("playlist_play",), text("keymap.tool_playlist_play")),
    PanelTool(("playlist_shuffle",), text("keymap.tool_playlist_shuffle")),
    PanelTool(("playlist_enqueue",), text("keymap.tool_playlist_enqueue")),
    PanelTool(("play_all",), text("keymap.tool_play_all")),
    PanelTool(("enqueue_all",), text("keymap.tool_enqueue_all")),
    PanelTool(("save_list",), text("keymap.tool_save_list")),
    PanelTool(("bookmark",), text("keymap.tool_bookmark")),
]


def tool_hints(applicable: set[str]) -> list[tuple[str, str]]:
    """Key and label pairs of the ``PANEL_TOOLS`` whose first action is in ``applicable``, in table order."""
    return [(" ".join(key_of(a) for a in t.actions), t.label) for t in PANEL_TOOLS if t.actions[0] in applicable]
