"""The keymap: the only place keys are bound in code. Prose lives in docs/features/keybindings.md."""

from __future__ import annotations

from textual.binding import Binding

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

FILTER = Binding("f", "filter", show=False)
RAIL = Binding("tab", "rail_toggle", show=False)

LIST_TOOLS = [
    Binding("m", "mark", show=False),
    Binding("M", "mark_page", show=False),
    Binding("D", "delete", show=False),
    Binding("u", "undo", show=False),
]

HISTORY_KEYS = [
    Binding("Y", "history_source", show=False),
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

SUBSCRIPTIONS = [Binding("F", "following", show=False)]

FOCUS_RECLAIM_KEYS = frozenset(
    {"j", "k", "h", "l", "up", "down", "left", "right", "enter", "g", "G", "H", "L"}
)
