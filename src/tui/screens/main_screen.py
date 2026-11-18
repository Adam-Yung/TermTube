from __future__ import annotations

import os
import threading

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Tab, Tabs

from src import history, logger
from src.entries import Entry
from src.plat import ProcessRegistry
from src.search_stack import SearchStack
from src.tui import keymap
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.debug_log import DebugLogMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.feed_loader import FEED_TABS, FeedLoaderMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.screens.mixins.list_tools import ListToolsMixin, Removal
from src.tui.widgets.app_header import AppHeader
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

_TABS = (
    ("home", "🏠 Home"),
    ("subscriptions", "📺 Subscriptions"),
    ("search", "🔍 Search"),
    ("history", "🕐 History"),
    ("library", "📁 Library"),
    ("playlists", "🎵 Playlists"),
    ("help", "📚 Help"),
)
_LOADABLE_TABS = ("home", "subscriptions", "history", "library", "playlists")
_FORCE_EXIT_AFTER_S = 2.0
_KILL_TIMEOUT_S = 1.5


def _force_exit() -> None:
    try:
        ProcessRegistry.get().kill_all(timeout=_KILL_TIMEOUT_S)
    except Exception:
        pass
    os._exit(0)


class MainScreen(
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
        *keymap.LIST_TOOLS,
        Binding("backspace,escape", "nav_back", show=False),
        Binding("grave_accent", "nav_picker", show=False),
        Binding("f1", "goto_tab('home')", show=False),
        Binding("f2", "goto_tab('subscriptions')", show=False),
        Binding("f3", "goto_tab('search')", show=False),
        Binding("f4", "goto_tab('history')", show=False),
        Binding("f5", "goto_tab('library')", show=False),
        Binding("f6", "goto_tab('playlists')", show=False),
        Binding("f7", "goto_tab('help')", show=False),
        Binding("ctrl+d", "toggle_log", "Debug", show=False),
        keymap.SEARCH,
        Binding("r", "refresh", "Refresh"),
        *keymap.GLOBAL,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_tab = ""
        self._search = SearchStack()
        self._nav_stack: list[str] = []
        self._opening_search_tab = False
        self._feed_session = 0
        self._avatar_session = 0
        self._active_workers = 0
        self._workers_lock = threading.Lock()
        self._init_detail_focus()
        self._init_debug_log()
        self._init_list_tools()

    def _removals(self) -> dict[str, Removal]:
        return {
            "history": Removal(
                remove=lambda entries: history.remove_many([e["id"] for e in entries if e.get("id")]),
                restore=history.restore,
                reload=history.all_entries,
                noun="video",
            ),
        }

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Tabs(*[Tab(label, id=tab_id) for tab_id, label in _TABS], id="nav-tabs")
        with Horizontal(id="main-content"):
            yield VideoListPanel(id="video-list-panel")
            yield DetailPanel(id="detail-panel")
        yield RichLog(id="debug-log", highlight=True, markup=True, max_lines=100, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        tabs = self.query_one("#nav-tabs", Tabs)
        tabs.can_focus = False
        for tab in tabs.query(Tab):
            tab.can_focus = False
        self._mount_debug_log()
        self.app.audio.log = self._log
        self._sync_player_bar()
        self.call_after_refresh(logger.stage, "first paint")
        self.call_after_refresh(self._maybe_show_image_warning)

    def on_unmount(self) -> None:
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
            elif choice == "settings":
                self.app.push_screen(SettingsModal())

        self.app.push_screen(EmptyFeedModal(), on_result)

    def _prompt_ytdlp_update(self, feed_key: str, error_detail: str = "") -> None:
        from src.tui.screens.ytdlp_update_modal import YtdlpUpdateModal

        def on_result(choice: str) -> None:
            if choice == "update":
                self._run_ytdlp_update(reload_tab=feed_key)
            else:
                self._list().set_error_message(
                    "⚠ Feed loading failed.\n\nTry updating manually:\n  termtube --update"
                )

        self.app.push_screen(YtdlpUpdateModal(error_detail), on_result)

    @work(thread=True)
    def _run_ytdlp_update(self, *, reload_tab: str | None = None) -> None:
        from src.updater import update_ytdlp

        call = self.app.call_from_thread
        call(self.notify, "Updating yt-dlp…", timeout=3)
        if not update_ytdlp(verbose=False):
            call(self.notify, "yt-dlp update failed. Try: termtube --update", severity="error", timeout=6)
        elif reload_tab:
            call(self.notify, "yt-dlp updated — reloading feed…", timeout=4)
            call(self._load_view, reload_tab)
        else:
            call(self.notify, "yt-dlp updated successfully.", timeout=5)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        # Appending list items can move focus onto the tab bar, which re-activates the
        # current tab. A real switch always changes the id.
        if not tab_id or tab_id == self._current_tab:
            return
        logger.info("tab → %s", tab_id)
        self._cancel_pending_focus_and_thumb()
        if tab_id == "search":
            if self._opening_search_tab:
                self._opening_search_tab = False
            elif not (self._current_tab == "search" and self._search.query):
                self._open_search_dialog()
        elif tab_id == "help":
            self._show_help(restore_tab=self._current_tab)
        else:
            if self._current_tab in FEED_TABS:
                self._save_feed_stash(self._current_tab)
            self._save_search_position()
            self._current_tab = tab_id
            self._nav_stack.clear()
            self._load_view(tab_id)

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
        current = "playlists" if self._current_tab.startswith("playlist:") else self._current_tab
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
        if not self._nav_stack:
            if self._current_tab == "search" and self._search.pop():
                self._show_search_frame()
            return
        previous = self._nav_stack.pop()
        self._current_tab = previous
        if previous == "search":
            self._load_view("search")
        else:
            self.query_one("#nav-tabs", Tabs).active = previous

    def action_search(self) -> None:
        self._open_search_dialog()

    def _open_search_dialog(self) -> None:
        from src.tui.screens.search_modal import SearchModal

        def on_result(query: str | None) -> None:
            # On cancel do not touch ``tabs.active``: re-activating the current tab reloads its list.
            if query:
                self._show_search_results(query)

        self.app.push_screen(SearchModal(), on_result)

    def _show_search_results(self, query: str) -> None:
        logger.info("search %r", query)
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self._save_search_position()
        self._search.push(query)
        self._current_tab = "search"
        self._nav_stack.clear()
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
                tab.label = f"🔍 {self._search.query[:20]}"
        tabs.active = "search"
        self._load_view("search")

    def _open_playlist(self, name: str) -> None:
        self._nav_stack.append(self._current_tab)
        self._current_tab = f"playlist:{name}"
        panel = self._list()
        panel.clear_and_set_loading()
        panel.set_breadcrumb(f"🎵 {name}  ← backspace to go back")
        self._detail().clear()
        self._start_view(f"playlist:{name}")

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
            self._open_playlist(entry.get("_playlist_name", ""))
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
        if self._current_tab in FEED_TABS:
            self.app.cache.clear_feed(self._current_tab)
            if self._current_tab == "home":
                self.app.cache.clear_home_stash()
        self._load_view(self._current_tab)
        self.notify(f"Refreshing {self._current_tab}…", timeout=2)

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
        timer = threading.Timer(_FORCE_EXIT_AFTER_S, _force_exit)
        timer.daemon = True
        timer.start()
        self.app.exit()

