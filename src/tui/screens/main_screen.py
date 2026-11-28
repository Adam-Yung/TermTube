from __future__ import annotations

import os
import threading
from functools import partial

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Tab, Tabs

from src import history, logger
from src.entries import Entry
from src.plat import ProcessRegistry
from src.strings import text
from src.tui import keymap, library_delete
from src.tui.screens.mixins.app_pages import AppPagesMixin
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.debug_log import DebugLogMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.feed_loader import FeedLoaderMixin
from src.tui.screens.mixins.feed_prompts import FeedPromptsMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.library_rail import LibraryRailMixin
from src.tui.screens.mixins.list_nav import ListNavMixin, lock_tab_bar
from src.tui.screens.mixins.list_tools import ListToolsMixin, Removal
from src.tui.screens.mixins.local_tab import LOCAL_TAB, LocalTabMixin
from src.tui.screens.mixins.playlist_tools import PlaylistToolsMixin
from src.tui.screens.mixins.search_tab import SearchTabMixin
from src.tui.screens.mixins.subscription_rows import SubscriptionRowsMixin
from src.tui.views import FEED_TABS, RAIL_TABS, feed_key_of, tab_of
from src.tui.widgets.app_header import AppHeader
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.library_rail import LibraryRail
from src.tui.widgets.video_list import VideoListPanel

_TABS = (
    ("home", text("main_screen.tab_home")),
    ("subscriptions", text("main_screen.tab_subscriptions")),
    ("search", text("main_screen.tab_search")),
    ("history", text("main_screen.tab_history")),
    ("library", text("main_screen.tab_library")),
    (LOCAL_TAB, text("main_screen.tab_local")),
    ("help", text("main_screen.tab_help")),
)
_LOADABLE_TABS = ("home", "subscriptions", "history", "library", LOCAL_TAB)
_VIEW_TOOLS = {
    "home": {"show_played"},
    "search": {"search_sort", "search_type"},
    "history": {"search_sort"},
    "history:yt": {"history_import"},
}
"""Tools a view has wherever the focus is; the list tools depend on focus and are added by ``_tool_actions``."""
_PLAYLIST_KEYS = frozenset({"playlist_rename", "playlist_play", "playlist_shuffle", "playlist_enqueue"})
_FORCE_EXIT_AFTER_S = 2.0
_KILL_TIMEOUT_S = 1.5


def _force_exit() -> None:
    try:
        ProcessRegistry.get().kill_all(timeout=_KILL_TIMEOUT_S)
    except Exception:
        pass
    os._exit(0)


class MainScreen(
    PlaylistToolsMixin,
    LibraryRailMixin,
    ListToolsMixin,
    ListNavMixin,
    DetailFocusMixin,
    ItemActionsMixin,
    AudioBarMixin,
    FeedLoaderMixin,
    DebugLogMixin,
    SearchTabMixin,
    SubscriptionRowsMixin,
    LocalTabMixin,
    FeedPromptsMixin,
    AppPagesMixin,
    Screen,
):
    """Tabs, the video list and the detail panel; the action bar mirrors ``app.audio``."""

    _LIST_ID = "#video-list-panel"
    _DETAIL_ID = "#detail-panel"

    BINDINGS = [
        *keymap.LIST_NAV,
        *keymap.PLAYBACK,
        *keymap.ITEM_ACTIONS,
        keymap.FILTER,
        keymap.RAIL,
        *keymap.LIST_TOOLS,
        *keymap.PLAYLIST_TOOLS,
        *keymap.HISTORY_KEYS,
        Binding("backspace,escape", "nav_back", show=False),
        Binding("grave_accent", "nav_picker", show=False),
        Binding("f1", "goto_tab('home')", show=False),
        Binding("f2", "goto_tab('subscriptions')", show=False),
        Binding("f3", "goto_tab('search')", show=False),
        Binding("f4", "goto_tab('history')", show=False),
        Binding("f5", "goto_tab('library')", show=False),
        Binding("f6", f"goto_tab('{LOCAL_TAB}')", show=False),
        Binding("f7", "goto_tab('help')", show=False),
        Binding("ctrl+d", "toggle_log", "Debug", show=False),
        keymap.SEARCH,
        *keymap.SEARCH_FILTERS,
        Binding("r", "refresh", "Refresh"),
        *keymap.HOME,
        *keymap.GLOBAL,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_tab = ""
        self._feed_session = 0
        self._avatar_session = 0
        self._active_workers = 0
        self._workers_lock = threading.Lock()
        self._init_detail_focus()
        self._init_debug_log()
        self._init_list_tools()
        self._init_library_rail()
        self._init_search_tab()
        self._init_local_tab()

    def _removals(self) -> dict[str, Removal]:
        return {
            "history": self._history_removal(),
            "library": library_delete.removal(self.app.config),
            "library:video": library_delete.removal(self.app.config, "video"),
            "library:audio": library_delete.removal(self.app.config, "audio"),
            LOCAL_TAB: self._local_removal(),
            **self._playlist_removals(),
        }

    def _history_removal(self) -> Removal:
        return Removal(
            remove=lambda entries, _choice: history.remove_many([e["id"] for e in entries if e.get("id")]),
            restore=history.restore,
            reload=lambda: history.ordered(history.all_entries(), self._history_sort),
            noun="video",
        )

    def _tool_actions(self) -> set[str]:
        """The tools that apply to this tab and focus: removal and marks where the tab can remove, its own keys."""
        view, on_rail = self._current_tab, self._rail_focused()
        playlist_shown = (self._rail_playlist() if on_rail else self._playlist_id()) is not None
        removable = playlist_shown if on_rail else view in self._removals()
        tools = set(_VIEW_TOOLS.get(view, set()))
        if removable:
            tools.add("delete")
        if not on_rail:
            tools.add("filter")
            if removable or view == "history:yt":
                tools.add("mark")
        if self._can_undo():
            tools.add("undo")
        if tab_of(view) == "library":
            tools.add("playlist_new")
        if playlist_shown:
            tools |= _PLAYLIST_KEYS
            if not on_rail:
                tools.add("playlist_move_down")
        return tools

    def panel_hints(self) -> list[tuple[str, str]]:
        if self._rail_focused():
            return [("⏎", text("main_screen.open_hint")), *keymap.tool_hints(self._tool_actions())]
        return super().panel_hints()

    def on_list_view_highlighted(self) -> None:
        self._refresh_actions()

    def on_library_rail_moved(self) -> None:
        self._refresh_actions()

    def on_descendant_focus(self) -> None:
        self._refresh_actions()

    def on_descendant_blur(self) -> None:
        self._refresh_actions()

    def _selected_entry(self) -> Entry | None:
        """The highlighted row; none while the rail has focus, so row actions never act on a row the user is not on."""
        return None if self._rail_focused() else super()._selected_entry()

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Tabs(*[Tab(label, id=tab_id) for tab_id, label in _TABS], id="nav-tabs")
        with Horizontal(id="main-content"):
            yield LibraryRail(id="library-rail")
            yield VideoListPanel(id="video-list-panel")
            yield DetailPanel(id="detail-panel")
        yield RichLog(id="debug-log", highlight=True, markup=True, max_lines=100, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        lock_tab_bar(self.query_one("#nav-tabs", Tabs))
        self._rail().display = False
        self._mount_debug_log()
        self.app.audio.log = self._log
        self._sync_player_bar()
        self.call_after_refresh(logger.stage, "first paint")
        self.call_after_refresh(self._maybe_show_image_warning)
        self.call_after_refresh(self._prewarm_cookies)

    def on_unmount(self) -> None:
        self.app.audio.detach_log(self._log)
        self._close_cursor()
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        # Appending list items can move focus onto the tab bar, which re-activates the
        # current tab. A real switch always changes the id.
        if not tab_id or tab_id == tab_of(self._current_tab):
            return
        logger.info("tab → %s", tab_id)
        self._cancel_pending_focus_and_thumb()
        if tab_id == "search":
            self._on_search_tab_activated()
        elif tab_id == "help":
            self._show_help(restore_tab=tab_of(self._current_tab))
        else:
            self._enter_tab(tab_id)

    def _on_search_tab_activated(self) -> None:
        if self._opening_search_tab:
            self._opening_search_tab = False
        elif not (self._current_tab == "search" and self._search.query):
            self._open_search_dialog()

    def _enter_tab(self, tab_id: str) -> None:
        """Leave the current view and load the one this tab shows."""
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self._save_search_position()
        self._show_rail(tab_id in RAIL_TABS)
        if tab_id in RAIL_TABS:
            self._select_collection(self._rail_views[tab_id], focus_list=False)
        else:
            self._current_tab = tab_id
            self._load_view(tab_id)

    def action_history_import(self) -> None:
        """I: copy the loaded YouTube history rows (or the marked ones) into the local history."""
        if self._current_tab != "history:yt":
            self._hint(text("main_screen.history_import_hint"), "information")
            return
        panel = self._list()
        rows = panel.marked_entries() or panel.visited_entries()
        added = history.import_entries(rows, self.app.config)
        self.notify(text("main_screen.imported", added=added, total=len(rows)), timeout=5)

    def _show_help(self, *, restore_tab: str = "") -> None:
        from src.tui.screens.help_screen import HelpScreen

        self.app.push_screen(HelpScreen(), partial(self._on_help_closed, restore_tab))

    def _on_help_closed(self, restore_tab: str, _result: None) -> None:
        if restore_tab:
            self.query_one("#nav-tabs", Tabs).active = restore_tab if restore_tab != "help" else "home"

    def action_goto_tab(self, tab_id: str) -> None:
        if tab_id == "search":
            self._open_search_dialog()
        elif tab_id == "help":
            self._show_help()
        else:
            self.query_one("#nav-tabs", Tabs).active = tab_id

    def action_tab_prev(self) -> None:
        self._cycle_tab(-1)

    def action_tab_next(self) -> None:
        self._cycle_tab(1)

    def _cycle_tab(self, step: int) -> None:
        current = tab_of(self._current_tab)
        order = list(_LOADABLE_TABS)
        if self._search.query:
            order.insert(2, "search")
        if current not in order:
            return
        target = order[(order.index(current) + step) % len(order)]
        if target == "search":
            self._show_search_results(self._search.query)
        else:
            self.action_goto_tab(target)

    def action_nav_picker(self) -> None:
        from src.tui.screens.nav_modal import NavModal

        self.app.push_screen(NavModal(), self._on_page_picked)

    def _on_page_picked(self, tab_id: str | None) -> None:
        if tab_id:
            self.action_goto_tab(tab_id)

    def action_nav_back(self) -> None:
        if self._close_filter_if_active():
            return
        if tab_of(self._current_tab) in RAIL_TABS:
            if not self._rail_focused():
                self._rail().focus()
        elif self._current_tab == "search" and self._search.pop():
            self._show_search_frame()
        elif self._current_tab == LOCAL_TAB:
            self._local_up()

    def _crumbs(self) -> list[str]:
        tab = tab_of(self._current_tab)
        labels = dict(_TABS)
        return [labels.get(tab, tab).split(" ", 1)[-1]]

    def action_show_played(self) -> None:
        """Home: show or hide the videos already played (the footer counts the hidden ones)."""
        if self._current_tab != "home":
            self._hint(text("main_screen.show_played_hint"), "information")
            return
        self._show_played = not self._show_played
        self._load_view("home")
        self.notify(text("main_screen.showing_played" if self._show_played else "main_screen.hiding_played"), timeout=2)

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        entry = message.entry
        if entry.get("_is_channel"):
            self._focus_channel(entry)
        else:
            self._focus_video(entry)
            self._refresh_queue_hint(entry)

    def _activate_entry(self, entry: Entry) -> None:
        if entry.get("_is_folder"):
            self._open_folder(entry)
        elif entry.get("_is_playlist"):
            self._open_playlist(entry)
        elif entry.get("_is_channel"):
            self._open_channel(entry)
        else:
            self._open_action_menu(entry)

    def _cancel_pending_focus_and_thumb(self) -> None:
        """Also invalidates the subscriptions avatar: it renders into the shared detail panel."""
        super()._cancel_pending_focus_and_thumb()
        self._avatar_session += 1

    def _worker_start(self) -> None:
        with self._workers_lock:
            self._active_workers += 1
        self._set_spinner(loading=True)

    def _worker_end(self) -> None:
        with self._workers_lock:
            self._active_workers = max(0, self._active_workers - 1)
            idle = self._active_workers == 0
        if idle:
            self._set_spinner(loading=False)

    def _set_spinner(self, *, loading: bool) -> None:
        try:
            header = self.query_one(AppHeader)
            self.app.call_from_thread(header.set_status_loading if loading else header.set_status_idle)
        except Exception:
            pass

    def action_refresh(self) -> None:
        logger.info("refresh %s", self._current_tab)
        if feed_key := feed_key_of(self._current_tab):
            self.app.cache.clear_feed(feed_key)
            if self._current_tab == "home":
                self.app.cache.clear_home_stash()
        self._load_view(self._current_tab)
        self.notify(text("main_screen.refreshing", tab=self._current_tab), timeout=2)

    def action_quit_app(self) -> None:
        logger.info("quit")
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self.app.audio.stop_audio()
        history.flush()
        timer = threading.Timer(_FORCE_EXIT_AFTER_S, _force_exit)
        timer.daemon = True
        timer.start()
        self.app.exit()

