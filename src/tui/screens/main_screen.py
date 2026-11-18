from __future__ import annotations

import os
import threading

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Tab, Tabs

from src import history, logger, search_history
from src.entries import Entry
from src.plat import ProcessRegistry
from src.search_stack import SearchStack
from src.strings import text
from src.tui import keymap, library_delete
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.debug_log import DebugLogMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.feed_loader import FEED_TABS, FeedLoaderMixin, feed_key_of
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.library_rail import HISTORY_SOURCES, LibraryRailMixin, tab_of
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.screens.mixins.list_tools import ListToolsMixin, Removal
from src.tui.screens.mixins.playlist_tools import PlaylistToolsMixin
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
    ("help", text("main_screen.tab_help")),
)
_SEARCH_SORTS = [
    ("relevance", text("main_screen.sort_relevance"), "r"),
    ("date", text("main_screen.sort_date"), "d"),
    ("views", text("main_screen.sort_views"), "v"),
]
_SEARCH_TYPES = [
    ("all", text("main_screen.type_all"), "a"),
    ("video", text("main_screen.type_video"), "v"),
    ("channel", text("main_screen.type_channel"), "c"),
    ("playlist", text("main_screen.type_playlist"), "p"),
]
_HISTORY_SORTS = [
    ("recent", text("main_screen.history_recent"), "r"),
    ("plays", text("main_screen.history_plays"), "m"),
    ("time", text("main_screen.history_time"), "l"),
]
_LOADABLE_TABS = ("home", "subscriptions", "history", "library")
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
        Binding("f6", "goto_tab('help')", show=False),
        Binding("ctrl+d", "toggle_log", "Debug", show=False),
        keymap.SEARCH,
        *keymap.SEARCH_FILTERS,
        Binding("r", "refresh", "Refresh"),
        *keymap.SUBSCRIPTIONS,
        *keymap.HOME,
        *keymap.GLOBAL,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_tab = ""
        self._search = SearchStack()
        self._opening_search_tab = False
        self._feed_session = 0
        self._avatar_session = 0
        self._active_workers = 0
        self._workers_lock = threading.Lock()
        self._init_detail_focus()
        self._init_debug_log()
        self._init_list_tools()
        self._init_library_rail()
        self._history_view = "history"
        self._history_sort = "recent"

    def _removals(self) -> dict[str, Removal]:
        return {
            "history": Removal(
                remove=lambda entries, _choice: history.remove_many([e["id"] for e in entries if e.get("id")]),
                restore=history.restore,
                reload=lambda: history.ordered(history.all_entries(), self._history_sort),
                noun="video",
            ),
            "library": library_delete.removal(self.app.config),
            "library:video": library_delete.removal(self.app.config, "video"),
            "library:audio": library_delete.removal(self.app.config, "audio"),
            **self._playlist_removals(),
        }

    def _tool_actions(self) -> set[str]:
        """The tools that apply to this tab and focus: removal and marks where the tab can remove, its own keys."""
        view, tab, on_rail = self._current_tab, tab_of(self._current_tab), self._rail_focused()
        playlist_shown = (self._rail_playlist() if on_rail else self._playlist_id()) is not None
        removable = playlist_shown if on_rail else view in self._removals()
        tools = {"delete"} if removable else set()
        if not on_rail:
            tools.add("filter")
            if removable or view == "history:yt":
                tools.add("mark")
        if view == "history:yt":
            tools.add("history_import")
        if self._can_undo():
            tools.add("undo")
        tools |= {"history": {"history_source"}, "home": {"show_played"}, "subscriptions": {"following"},
                  "search": {"search_sort", "search_type"}}.get(tab if tab == "history" else view, set())
        if view == "history":
            tools.add("search_sort")
        if tab == "library":
            tools.add("playlist_new")
        if playlist_shown:
            tools |= {"playlist_rename", "playlist_play", "playlist_shuffle", "playlist_enqueue"}
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
        tabs = self.query_one("#nav-tabs", Tabs)
        tabs.can_focus = False
        for tab in tabs.query(Tab):
            tab.can_focus = False
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

    def _maybe_show_image_warning(self) -> None:
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        config = self.app.config
        if _HAS_TEXTUAL_IMAGE or config.get("thumbnail_warning_dismissed", False):
            return
        from src.tui.screens.image_warning_modal import ImageWarningModal

        def on_done(never_show: bool) -> None:
            if never_show:
                config.set("thumbnail_warning_dismissed", True)
                config.save()

        self.app.push_screen(ImageWarningModal(), on_done)

    def _show_empty_feed_modal(self, feed_key: str) -> None:
        from src.tui.screens.empty_feed_modal import EmptyFeedModal
        from src.tui.screens.settings_modal import SettingsModal

        def on_result(choice: str) -> None:
            if choice == "update":
                self._run_ytdlp_update(reload_tab=feed_key)
            elif choice == "refresh":
                self._refresh_account(feed_key)
            elif choice == "settings":
                self.app.push_screen(SettingsModal())

        self.app.push_screen(EmptyFeedModal(), on_result)

    def _prewarm_cookies(self) -> None:
        from src import cookies

        cookies.prewarm(self.app.config)

    def _refresh_account(self, feed_key: str) -> None:
        """Forget the cookie jar (the next load re-reads the browser) and reload the feed."""
        from src import cookies

        cookies.invalidate()
        self.app.cache.clear_feed(feed_key)
        self._load_view(self._current_tab)

    def _prompt_ytdlp_update(self, feed_key: str, error_detail: str = "") -> None:
        from src.tui.screens.ytdlp_update_modal import YtdlpUpdateModal

        def on_result(choice: str) -> None:
            if choice == "update":
                self._run_ytdlp_update(reload_tab=feed_key)
            else:
                self._list().set_error_message(text("main_screen.feed_failed"))

        self.app.push_screen(YtdlpUpdateModal(error_detail), on_result)

    @work(thread=True)
    def _run_ytdlp_update(self, *, reload_tab: str | None = None) -> None:
        from src.updater import update_ytdlp

        call = self.app.call_from_thread
        call(self.notify, text("main_screen.updating_ytdlp"), timeout=3)
        if not update_ytdlp(verbose=False):
            call(self.notify, text("main_screen.ytdlp_update_failed"), severity="error", timeout=6)
        elif reload_tab:
            call(self.notify, text("main_screen.ytdlp_updated_reloading"), timeout=4)
            call(self._load_view, reload_tab)
        else:
            call(self.notify, text("main_screen.ytdlp_updated"), timeout=5)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        # Appending list items can move focus onto the tab bar, which re-activates the
        # current tab. A real switch always changes the id.
        if not tab_id or tab_id == tab_of(self._current_tab):
            return
        logger.info("tab → %s", tab_id)
        self._cancel_pending_focus_and_thumb()
        if tab_id == "search":
            if self._opening_search_tab:
                self._opening_search_tab = False
            elif not (self._current_tab == "search" and self._search.query):
                self._open_search_dialog()
        elif tab_id == "help":
            self._show_help(restore_tab=tab_of(self._current_tab))
        else:
            if self._current_tab in FEED_TABS:
                self._save_feed_stash(self._current_tab)
            self._save_search_position()
            self._show_rail(tab_id == "library")
            if tab_id == "library":
                self._select_collection(self._library_view, focus_list=False)
            else:
                self._current_tab = self._history_view if tab_id == "history" else tab_id
                self._load_view(self._current_tab)

    def action_history_source(self) -> None:
        """Y: cycle the History tab's source (Local, then each YouTube account list)."""
        if tab_of(self._current_tab) != "history":
            self._hint(text("main_screen.history_source_hint"), "information")
            return
        self._cancel_pending_focus_and_thumb()
        sources = HISTORY_SOURCES
        self._current_tab = self._history_view = sources[(sources.index(self._current_tab) + 1) % len(sources)]
        self._load_view(self._current_tab)

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

        def on_close(_: None) -> None:
            if restore_tab:
                self.query_one("#nav-tabs", Tabs).active = restore_tab if restore_tab != "help" else "home"

        self.app.push_screen(HelpScreen(), on_close)

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

        def on_pick(tab_id: str | None) -> None:
            if tab_id:
                self.action_goto_tab(tab_id)

        self.app.push_screen(NavModal(), on_pick)

    def action_nav_back(self) -> None:
        if self._close_filter_if_active():
            return
        if self._current_tab == "following":
            self._current_tab = "subscriptions"
            self._load_view("subscriptions")
        elif tab_of(self._current_tab) == "library":
            if not self._rail_focused():
                self._rail().focus()
        elif self._current_tab == "search" and self._search.pop():
            self._show_search_frame()

    def action_search(self) -> None:
        self._open_search_dialog()

    def action_search_sort(self) -> None:
        if self._current_tab == "history":
            self._pick_history_sort()
        else:
            self._pick_search_filter("sort", text("main_screen.sort_results_title"), _SEARCH_SORTS, self._search.sort)

    def _pick_history_sort(self) -> None:
        """s on the local History tab: recent (with day headers), most watched or longest watched."""
        from src.tui.screens.sort_modal import SortModal

        def on_pick(value: str | None) -> None:
            if value and value != self._history_sort:
                self._history_sort = value
                self._load_view("history")

        title = text("main_screen.sort_history_title")
        self.app.push_screen(SortModal(self._history_sort, options=_HISTORY_SORTS, title=title), on_pick)

    def action_search_type(self) -> None:
        self._pick_search_filter("kind", text("main_screen.result_type_title"), _SEARCH_TYPES, self._search.kind)

    def _pick_search_filter(self, field: str, title: str, options: list[tuple[str, str, str]], current: str) -> None:
        """Ask for a sort or type and reload the current search with it (Search tab only)."""
        if self._current_tab != "search" or not self._search.query:
            self._hint(text("main_screen.search_filter_hint"), "information")
            return
        from src.tui.screens.sort_modal import SortModal

        def on_pick(value: str | None) -> None:
            if value and value != current:
                self._search.set_filter(field, value)
                self._show_search_frame()

        self.app.push_screen(SortModal(current, options=options, title=title), on_pick)

    def _open_search_dialog(self) -> None:
        from src.tui.screens.search_modal import SearchModal

        def on_result(query: str | None) -> None:
            # On cancel do not touch ``tabs.active``: re-activating the current tab reloads its list.
            if query:
                search_history.add(query, self.app.config)
                self._show_search_results(query)

        self.app.push_screen(SearchModal(), on_result)

    def _show_search_results(self, query: str) -> None:
        logger.info("search %r", query)
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self._save_search_position()
        self._search.push(query)
        self._current_tab = "search"
        self._show_rail(False)
        self._opening_search_tab = True
        self._show_search_frame()

    def _save_search_position(self) -> None:
        """Remember the page and row of the results being left, so coming back lands there."""
        if self._current_tab != "search" or not self._search.query:
            return
        row = self._list().selected_entry
        self._search.save_position(self._list().current_page, row.get("id") if row else None)

    def _show_search_frame(self) -> None:
        """Show the current search on the Search tab (its results come from the cache when they are fresh)."""
        tabs = self.query_one("#nav-tabs", Tabs)
        for tab in tabs.query(Tab):
            if tab.id == "search":
                tab.label = text("main_screen.tab_search_query", query=self._search.query[:20])
        tabs.active = "search"
        self._load_view("search")

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

    def action_following(self) -> None:
        """The local Following list, from the Subscriptions tab (it needs no account)."""
        if self._current_tab != "subscriptions":
            self._hint(text("main_screen.following_hint"), "information")
            return
        self._current_tab = "following"
        self._load_view("following")
        self._list().set_breadcrumb(text("main_screen.following_crumb"))
    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        entry = message.entry
        if entry.get("_is_channel"):
            self._focus_channel(entry)
        else:
            self._focus_video(entry)
            self._refresh_queue_hint(entry)

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()

    def _activate_entry(self, entry: Entry) -> None:
        if entry.get("_is_playlist"):
            self._hint(text("main_screen.open_playlist_in_browser"), "information")
        elif entry.get("_is_channel"):
            self._open_channel(entry)
        else:
            self._open_action_menu(entry)

    def _cancel_pending_focus_and_thumb(self) -> None:
        """Also invalidates the subscriptions avatar: it renders into the shared detail panel."""
        super()._cancel_pending_focus_and_thumb()
        self._avatar_session += 1

    def _focus_channel(self, entry: Entry) -> None:
        vid = entry.get("id", "")
        detail = self._detail()
        detail.update_channel_entry(entry)
        self._cancel_pending_focus_and_thumb()
        if vid:
            detail.set_thumbnail_video_id(vid)
            detail.set_thumbnail_loading()
        self._load_channel_avatar(vid, entry.get("thumbnail", ""), entry)

    def _load_channel_avatar(self, vid: str, thumb_url: str, entry: Entry) -> None:
        if not vid:
            return
        if thumb_url:
            self._avatar_session += 1
            self._avatar_worker(vid, thumb_url, self._avatar_session)
        if not entry.get("description") or not thumb_url:
            self._channel_info_worker(vid, entry)

    @work(thread=True, exclusive=True, group="ch_thumb")
    def _avatar_worker(self, vid: str, url: str, session: int) -> None:
        from src.tui.thumb_loader import load_thumbnail

        detail = self._detail()
        cols, rows = detail.thumbnail_cell_size()
        load_thumbnail(
            self.app, detail, vid, url=url, cols=cols, rows=rows,
            is_current=lambda: session == self._avatar_session,
        )

    @work(thread=True, exclusive=True, group="ch_focus")
    def _channel_info_worker(self, vid: str, entry: Entry) -> None:
        import src.ytdlp as ytdlp

        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            return
        self._worker_start()
        try:
            info = ytdlp.fetch_channel_info(url, self.app.config, self.app.cache)
            if info:
                self.app.call_from_thread(self._apply_channel_info, vid, info)
        except Exception as exc:
            logger.debug("channel info %s: %s", vid, exc)
        finally:
            self._worker_end()

    def _apply_channel_info(self, vid: str, info: dict) -> None:
        detail = self._detail()
        if detail.current_id != vid:
            return
        merged = {**(detail.last_entry or {}), **info}
        detail.update_channel_entry(merged)
        thumb_url = merged.get("thumbnail", "")
        if thumb_url:
            self._avatar_session += 1
            self._avatar_worker(vid, thumb_url, self._avatar_session)

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

    def action_help(self) -> None:
        self._show_help()

    def action_settings(self) -> None:
        from src.tui.screens.settings_modal import SettingsModal

        self.app.push_screen(SettingsModal())

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

