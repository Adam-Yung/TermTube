"""TermTube v2 — MainScreen.

The primary screen pushed by TermTubeApp.  Owns:
  - Feed tab bar (Home, Subscriptions, Search, Library, History)
  - VideoListPanel (left) + DetailPanel (right) layout
  - MiniPlayer (bottom)
  - AppHeader (top)
  - All worker threads for fetching, metadata, thumbnails, playback
  - Keyboard bindings for the entire app

Threading model
---------------
Every network / yt-dlp call runs inside @work(thread=True).
UI updates from threads use self.app.call_from_thread().
Cancellation is done via threading.Event objects.
"""
from __future__ import annotations

import threading
import webbrowser
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Tab, Tabs

import cache as _cache
import hidden as _hidden
import history as _history
import library as _library
import playlist as _playlist
import search_history as _search_history
import sponsorblock as _sb
import ytdlp as _ytdlp
import logger
from config import Config
from player import PlayMode, get_session
from tui.components.app_header import AppHeader
from tui.components.mini_player import MiniPlayer
from tui.components.notification_bar import NotificationBar
from tui.panels.detail_panel import DetailPanel
from tui.panels.video_list_panel import VideoListPanel


# Feed tab IDs
TAB_HOME = "tab-home"
TAB_SUBS = "tab-subs"
TAB_SEARCH = "tab-search"
TAB_LIBRARY = "tab-library"
TAB_HISTORY = "tab-history"

TAB_ORDER = [TAB_HOME, TAB_SUBS, TAB_SEARCH, TAB_LIBRARY, TAB_HISTORY]


class MainScreen(Screen):
    """Primary application screen."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("comma", "settings", "Settings"),
        Binding("/", "search", "Search"),
        Binding("r", "refresh", "Refresh"),
        Binding("R", "hard_refresh", "Hard refresh", show=False),
        Binding("f1", "tab_home", "Home", show=False),
        Binding("f2", "tab_subs", "Subscriptions", show=False),
        Binding("f3", "tab_search", "Search", show=False),
        Binding("f4", "tab_library", "Library", show=False),
        Binding("f5", "tab_history", "History", show=False),
        Binding("0", "seek_pct_0", show=False),
        Binding("1", "seek_pct_10", show=False),
        Binding("2", "seek_pct_20", show=False),
        Binding("3", "seek_pct_30", show=False),
        Binding("4", "seek_pct_40", show=False),
        Binding("5", "seek_pct_50", show=False),
        Binding("6", "seek_pct_60", show=False),
        Binding("7", "seek_pct_70", show=False),
        Binding("8", "seek_pct_80", show=False),
        Binding("9", "seek_pct_90", show=False),
        Binding("enter", "action_menu", "Actions"),
        Binding("l", "play_or_seek_fwd", "Listen / +5s"),
        Binding("w", "play_video", "Watch"),
        Binding("d", "download_video", "Download video", show=False),
        Binding("a", "download_audio", "Download audio", show=False),
        Binding("p", "add_playlist", "Playlist", show=False),
        Binding("x", "hide_video", "Hide", show=False),
        Binding("y", "copy_url", "Copy URL", show=False),
        Binding("b", "open_browser", "Browser", show=False),
        Binding("c", "go_channel", "Channel", show=False),
        Binding("e", "enqueue", "Enqueue", show=False),
        Binding("greater_than", "skip_next", "Next in queue", show=False),
        Binding("space", "pause_toggle", "Pause", show=False),
        Binding("h", "seek_back_small", "−5s", show=False),
        Binding("H", "seek_back_large", "−30s", show=False),
        Binding("L", "seek_fwd_large", "+30s", show=False),
        Binding("W", "play_video_quality", "Watch (quality)", show=False),
        Binding("[", "vol_down", "Vol−", show=False),
        Binding("]", "vol_up", "Vol+", show=False),
        Binding("s", "stop_playback", "Stop", show=False),
        Binding("m", "add_bookmark", "Bookmark", show=False),
        Binding("B", "jump_bookmark", "Jump to bookmark", show=False),
        Binding("J", "page_next", "Next page", show=False),
        Binding("K", "page_prev", "Prev page", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("ctrl+d", "toggle_debug", "Debug", show=False),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #main-tabs {
        height: 3;
        dock: top;
    }
    #main-columns {
        height: 1fr;
        layout: horizontal;
    }
    """

    def __init__(self, config: Config, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._theme = config.get("theme", "crimson")

        # Feed state
        self._active_tab = TAB_HOME
        self._current_page: dict[str, int] = {t: 1 for t in TAB_ORDER}
        self._total_pages: dict[str, int] = {t: 1 for t in TAB_ORDER}
        self._current_query = ""  # active search query
        self._focused_entry: dict | None = None

        # Cancellation tokens
        self._feed_cancel = threading.Event()
        self._meta_cancel = threading.Event()
        self._thumb_cancel = threading.Event()

        # Playback
        self._player = get_session()
        self._now_playing_id: str | None = None
        self._now_playing_mode: str = ""
        self._queue: list[dict] = []  # entries awaiting playback

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield AppHeader(theme=self._theme, id="app-header")
        yield Tabs(
            Tab("Home", id=TAB_HOME),
            Tab("Subscriptions", id=TAB_SUBS),
            Tab("Search", id=TAB_SEARCH),
            Tab("Library", id=TAB_LIBRARY),
            Tab("History", id=TAB_HISTORY),
            id="main-tabs",
        )
        with Horizontal(id="main-columns"):
            yield VideoListPanel(theme=self._theme, id="video-list")
            yield DetailPanel(theme=self._theme, id="detail-panel")
        yield NotificationBar(id="notify-bar")
        yield MiniPlayer(theme=self._theme, id="mini-player")
        yield Footer()

    def on_mount(self) -> None:
        vl = self.query_one("#video-list", VideoListPanel)
        vl.set_dirs(self._config.video_dir, self._config.audio_dir)
        self._register_player_callbacks()
        self._load_tab(TAB_HOME)
        self._check_cookies()

    @work(thread=True, group="cookies")
    def _check_cookies(self) -> None:
        """Check cookie freshness on mount and update the AppHeader dot."""
        from cookies import CookieManager
        mgr = CookieManager(self._config)
        status = mgr.status()
        self.app.call_from_thread(
            self._set_cookie_status, status
        )
        if status in ("stale", "missing"):
            browser = self._config.get("browser", "")
            if browser:
                ok = mgr.auto_refresh(browser)
                new_status = "ok" if ok else status
                self.app.call_from_thread(
                    self._set_cookie_status, new_status
                )

    def _set_cookie_status(self, status: str) -> None:
        try:
            self.query_one("#app-header", AppHeader).cookie_status = status
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab is None:
            return
        tab_id = event.tab.id
        if tab_id and tab_id != self._active_tab:
            self._active_tab = tab_id
            self._load_tab(tab_id)

    def _load_tab(self, tab_id: str) -> None:
        """Switch to tab and trigger feed load."""
        if tab_id == TAB_LIBRARY:
            self._load_library()
        elif tab_id == TAB_HISTORY:
            self._load_history()
        else:
            page = self._current_page.get(tab_id, 1)
            self._fetch_feed(tab_id, page)

    def _feed_source_for_tab(self, tab_id: str) -> str:
        """Return yt-dlp source string for the given tab."""
        if tab_id == TAB_HOME:
            return "home"
        if tab_id == TAB_SUBS:
            return "subscriptions"
        if tab_id == TAB_SEARCH:
            return self._current_query or ""
        return ""

    # ------------------------------------------------------------------
    # Feed workers
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="feed")
    def _fetch_feed(self, tab_id: str, page: int) -> None:
        """Worker: fetch one page of the given feed."""
        source = self._feed_source_for_tab(tab_id)
        if not source:
            self.app.call_from_thread(
                self.query_one("#video-list", VideoListPanel).load_entries,
                [],
                feed_key=tab_id,
                page=1,
                total_pages=1,
            )
            return

        self._feed_cancel.set()
        self._feed_cancel = threading.Event()
        cancel = self._feed_cancel

        self.app.call_from_thread(
            self.query_one("#video-list", VideoListPanel).set_loading, True
        )
        self.app.call_from_thread(
            self.query_one("#app-header", AppHeader).set_loading, True
        )

        try:
            entries, has_more = _ytdlp.fetch_page(
                source, page, self._config, cancel_event=cancel
            )
        except Exception as exc:
            logger.warning("feed fetch error: %s", exc)
            entries, has_more = [], False

        if cancel.is_set():
            return

        # Filter hidden videos on home/subs feeds
        if tab_id in (TAB_HOME, TAB_SUBS):
            entries = [e for e in entries if not _hidden.is_hidden(e.get("id", ""))]

        total = self._total_pages.get(tab_id, 1)
        if has_more and page >= total:
            total = page + 1
        elif not has_more:
            total = page
        self._total_pages[tab_id] = total
        self._current_page[tab_id] = page

        self.app.call_from_thread(
            self.query_one("#video-list", VideoListPanel).load_entries,
            entries,
            feed_key=source,
            page=page,
            total_pages=total,
            loading=False,
        )
        self.app.call_from_thread(
            self.query_one("#app-header", AppHeader).set_loading, False
        )

        if entries:
            first = entries[0]
            self.app.call_from_thread(self._on_entry_focused, first)

        # Prefetch next page in background
        if has_more and not cancel.is_set():
            self._prefetch_next(tab_id, page + 1, source)

    @work(thread=True, group="prefetch")
    def _prefetch_next(self, tab_id: str, next_page: int, source: str) -> None:
        """Pre-warm the cache for page N+1."""
        if self._feed_cancel.is_set():
            return
        self.app.call_from_thread(
            self.query_one("#video-list", VideoListPanel).set_prefetching, True
        )
        try:
            _ytdlp.fetch_page(source, next_page, self._config)
        except Exception:
            pass
        self.app.call_from_thread(
            self.query_one("#video-list", VideoListPanel).set_prefetching, False
        )

    def _load_library(self) -> None:
        try:
            entries = _library.all_entries(self._config.video_dir, self._config.audio_dir)
        except Exception:
            entries = []
        vl = self.query_one("#video-list", VideoListPanel)
        vl.load_entries(entries, feed_key="library", page=1, total_pages=1)
        vl.set_header(" Local Library")
        if entries:
            self._on_entry_focused(entries[0])

    def _load_history(self) -> None:
        try:
            entries = list(_history.all_entries())[:self._config.page_size * 5]
        except Exception:
            entries = []
        vl = self.query_one("#video-list", VideoListPanel)
        vl.load_entries(entries, feed_key="history", page=1, total_pages=1)
        vl.set_header(" Watch History")
        if entries:
            self._on_entry_focused(entries[0])


    # ------------------------------------------------------------------
    # Entry focus / metadata / thumbnail workers
    # ------------------------------------------------------------------

    def _on_entry_focused(self, entry: dict) -> None:
        """Called when cursor moves to a new entry (main thread or via call_from_thread)."""
        self._focused_entry = entry
        dp = self.query_one("#detail-panel", DetailPanel)
        dp.update_basic(entry)
        dp.set_thumbnail_loading()
        vid = entry.get("id", "")
        if vid:
            self._fetch_metadata(vid)
            self._fetch_thumb(vid, entry.get("thumbnail") or entry.get("thumbnails", [{}])[-1].get("url", "") if entry.get("thumbnails") else entry.get("thumbnail", ""))

    def on_video_list_panel_selected(self, event: VideoListPanel.Selected) -> None:
        self._on_entry_focused(event.entry)

    def on_video_list_panel_activated(self, event: VideoListPanel.Activated) -> None:
        self._on_entry_focused(event.entry)
        self.action_action_menu()

    def on_video_list_panel_page_change_requested(
        self, event: VideoListPanel.PageChangeRequested
    ) -> None:
        tab = self._active_tab
        page = self._current_page.get(tab, 1) + event.direction
        if page < 1:
            return
        total = self._total_pages.get(tab, 1)
        if page > total:
            return
        self._fetch_feed(tab, page)

    @work(thread=True, exclusive=True, group="meta")
    def _fetch_metadata(self, video_id: str) -> None:
        self._meta_cancel.set()
        self._meta_cancel = threading.Event()
        cancel = self._meta_cancel

        entry = _ytdlp.fetch_full(video_id, self._config, cancel_event=cancel)
        if cancel.is_set() or entry is None:
            return

        if self._focused_entry and self._focused_entry.get("id") == video_id:
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).refresh_metadata, entry
            )
            self.app.call_from_thread(
                self.query_one("#video-list", VideoListPanel).update_entry_by_id,
                video_id, entry,
            )

    @work(thread=True, exclusive=True, group="thumb")
    def _fetch_thumb(self, video_id: str, thumb_url: str) -> None:
        self._thumb_cancel.set()
        self._thumb_cancel = threading.Event()

        if _cache.has_thumb(video_id):
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).set_thumbnail, video_id
            )
            return

        if not thumb_url:
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).set_thumbnail_placeholder
            )
            return

        ok = _ytdlp.download_thumb(video_id, thumb_url)
        if ok:
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).set_thumbnail, video_id
            )
        else:
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).set_thumbnail_placeholder
            )

    def on_detail_panel_channel_requested(self, event: DetailPanel.ChannelRequested) -> None:
        from tui.screens.channel_screen import ChannelScreen
        self.app.push_screen(ChannelScreen(event.channel_url, event.channel_name, self._config))


    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _register_player_callbacks(self) -> None:
        sess = self._player
        sess.clear_callbacks()
        sess.on_property(self._on_player_property)
        sess.on_end(self._on_player_end)
        sess.on_error(self._on_player_error)
        sess.on_skip(self._on_sponsorblock_skip)

    def _on_player_property(self, event) -> None:
        """Called from mpv IPC reader thread."""
        state = self._player.state
        self.app.call_from_thread(
            self.query_one("#mini-player", MiniPlayer).update_position,
            state.position, state.duration, state.paused,
        )
        if event.name == "volume":
            self.app.call_from_thread(
                self.query_one("#mini-player", MiniPlayer).update_volume,
                state.volume,
            )

    def _on_player_end(self, returncode: int) -> None:
        last_mode = self._now_playing_mode
        self._now_playing_id = None
        self._now_playing_mode = ""
        if self._queue:
            next_entry = self._queue.pop(0)
            self.app.call_from_thread(
                self.query_one("#mini-player", MiniPlayer).update_queue,
                len(self._queue),
            )
            if last_mode == "VIDEO":
                self.app.call_from_thread(self._start_video, next_entry)
            else:
                self.app.call_from_thread(self._start_audio, next_entry)
        else:
            self.app.call_from_thread(
                self.query_one("#mini-player", MiniPlayer).set_idle
            )

    def _on_player_error(self, message: str) -> None:
        self._now_playing_id = None
        self._now_playing_mode = ""
        self.app.call_from_thread(
            self.query_one("#mini-player", MiniPlayer).set_idle
        )
        self.app.call_from_thread(
            self._notify_error, "Playback error", message
        )

    def _on_sponsorblock_skip(self, segment: dict) -> None:
        """Called from sb-skip thread when a segment is auto-skipped."""
        cat = segment.get("category", "segment")
        label = cat.replace("_", " ").capitalize()
        self.app.call_from_thread(
            self._notify, f"Skipped: {label}", "skip"
        )

    @work(thread=True, group="audio")
    def _start_audio(self, entry: dict, *, force_format: str | None = None) -> None:
        vid = entry.get("id", "")
        title = entry.get("title", "")
        channel = entry.get("channel") or entry.get("uploader", "")
        url = f"https://www.youtube.com/watch?v={vid}"

        # Format negotiation memory
        ytdl_format = force_format
        if not ytdl_format and vid:
            ytdl_format = _cache.get_last_quality(vid, "audio")
        if not ytdl_format:
            ytdl_format = self._config.preferred_audio_quality
        if vid and ytdl_format != self._config.preferred_audio_quality:
            _cache.set_last_quality(vid, "audio", ytdl_format)

        segments: list[dict] = []
        bookmarks: list[float] = []
        if self._config.sponsorblock_enabled:
            try:
                segs = _sb.fetch_segments(vid, self._config.sponsorblock_categories, self._config.ttl("sponsorblock"))
                segments = list(segs)
            except Exception:
                pass
        try:
            bms = _history.get_bookmarks(vid)
            bookmarks = [b["position"] for b in bms]
        except Exception:
            pass

        self._now_playing_id = vid
        self._now_playing_mode = "AUDIO"

        self._player.set_segments(
            segments,
            enabled=self._config.sponsorblock_enabled and bool(segments),
        )

        self.app.call_from_thread(
            self.query_one("#mini-player", MiniPlayer).set_playing,
            mode="AUDIO",
            title=title,
            channel=channel,
            volume=self._player.state.volume,
            segments=segments,
            bookmarks=bookmarks,
        )

        _history.add(entry)

        self._player.play_audio(
            url,
            title=title,
            cookie_args=self._config.cookie_args,
            ytdl_format=ytdl_format,
        )

    @work(thread=True, group="video")
    def _start_video(self, entry: dict, *, force_format: str | None = None) -> None:
        """Launch video in a separate mpv window — TUI stays fully live."""
        vid = entry.get("id", "")
        title = entry.get("title", "")
        channel = entry.get("channel") or entry.get("uploader", "")
        url = f"https://www.youtube.com/watch?v={vid}"

        # Format negotiation memory
        ytdl_format = force_format
        if not ytdl_format and vid:
            ytdl_format = _cache.get_last_quality(vid, "video")
        if not ytdl_format:
            ytdl_format = self._config.preferred_quality
        if vid and ytdl_format != self._config.preferred_quality:
            _cache.set_last_quality(vid, "video", ytdl_format)

        segments: list[dict] = []
        bookmarks: list[float] = []
        if self._config.sponsorblock_enabled:
            try:
                segs = _sb.fetch_segments(vid, self._config.sponsorblock_categories, self._config.ttl("sponsorblock"))
                segments = list(segs)
            except Exception:
                pass
        try:
            bms = _history.get_bookmarks(vid)
            bookmarks = [b["position"] for b in bms]
        except Exception:
            pass

        self._now_playing_id = vid
        self._now_playing_mode = "VIDEO"

        self._player.set_segments(
            segments,
            enabled=self._config.sponsorblock_enabled and bool(segments),
        )

        self.app.call_from_thread(
            self.query_one("#mini-player", MiniPlayer).set_playing,
            mode="VIDEO",
            title=title,
            channel=channel,
            volume=self._player.state.volume,
            segments=segments,
            bookmarks=bookmarks,
        )

        _history.add(entry)

        self._player.play_video(
            url,
            title=title,
            cookie_args=self._config.cookie_args,
            ytdl_format=ytdl_format,
        )

    # MiniPlayer events
    def on_mini_player_seek_requested(self, event: MiniPlayer.SeekRequested) -> None:
        if self._player.is_playing:
            self._player.seek_percent(event.fraction * 100)

    def on_mini_player_volume_change_requested(self, event: MiniPlayer.VolumeChangeRequested) -> None:
        if self._player.is_playing:
            step = self._config.volume_step
            if event.delta > 0:
                self._player.volume_up(step)
            else:
                self._player.volume_down(step)


    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    @work(thread=True, group="download")
    def _run_download(self, entry: dict, mode: str, fmt: str | None, modal) -> None:
        """Worker: execute yt-dlp download, report progress to DownloadModal."""
        vid = entry.get("id", "")

        def on_progress(info: dict) -> None:
            if modal.cancel_event.is_set():
                return
            self.app.call_from_thread(modal.on_progress, info)

        if mode == "video":
            ok = _ytdlp.download_video(vid, self._config, quality_format=fmt, on_progress=on_progress)
        else:
            ok = _ytdlp.download_audio(vid, self._config, quality_format=fmt, on_progress=on_progress)

        self.app.call_from_thread(modal.on_complete, ok)

    def _open_download_modal(self, entry: dict, mode: str, fmt: str | None = None) -> None:
        from tui.modals.download_modal import DownloadModal
        title = entry.get("title", "")
        modal = DownloadModal(entry.get("id", ""), title, mode=mode)

        def after_push(_) -> None:
            self._run_download(entry, mode, fmt, modal)

        self.app.push_screen(modal, after_push)

    # ------------------------------------------------------------------
    # Keyboard action handlers
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        self._player.stop()
        self.app.exit()

    def action_help(self) -> None:
        from tui.modals.help_screen import HelpScreen
        self.app.push_screen(HelpScreen())

    def action_settings(self) -> None:
        from tui.modals.settings_modal import SettingsModal
        def on_close(_) -> None:
            new_theme = self._config.get("theme", "crimson")
            if new_theme != self._theme:
                self._theme = new_theme
                self.query_one("#video-list", VideoListPanel).set_theme(new_theme)
                self.query_one("#detail-panel", DetailPanel).set_theme(new_theme)
                self.query_one("#mini-player", MiniPlayer).set_theme(new_theme)
        self.app.push_screen(SettingsModal(self._config), on_close)

    def action_cookies(self) -> None:
        from tui.modals.cookies_modal import CookiesModal
        self.app.push_screen(CookiesModal(self._config))

    def action_search(self) -> None:
        from tui.modals.search_modal import SearchModal
        recent = _search_history.all_queries(self._config.search_history_count)

        def on_result(query: str | None) -> None:
            if not query:
                return
            _search_history.add(query, self._config.search_history_count)
            self._current_query = query
            self._current_page[TAB_SEARCH] = 1
            self._total_pages[TAB_SEARCH] = 1
            try:
                self.query_one("#main-tabs", Tabs).active = TAB_SEARCH
            except Exception:
                self._active_tab = TAB_SEARCH
                self._fetch_feed(TAB_SEARCH, 1)

        self.app.push_screen(SearchModal(recent), on_result)

    def action_refresh(self) -> None:
        """r: Refresh current feed (re-fetch current page, uses cache for speed)."""
        tab = self._active_tab
        page = self._current_page.get(tab, 1)
        self._fetch_feed(tab, page)

    def action_hard_refresh(self) -> None:
        """R: Hard refresh — clear page cache, stash, and re-fetch from scratch."""
        tab = self._active_tab
        source = self._feed_source_for_tab(tab)
        _cache.invalidate_feed(source)
        _cache.clear_stash(source)
        self._current_page[tab] = 1
        self._total_pages[tab] = 1
        self._fetch_feed(tab, 1)

    def action_tab_home(self) -> None:
        self.query_one("#main-tabs", Tabs).active = TAB_HOME

    def action_tab_subs(self) -> None:
        self.query_one("#main-tabs", Tabs).active = TAB_SUBS

    def action_tab_search(self) -> None:
        self.action_search()

    def action_tab_library(self) -> None:
        self.query_one("#main-tabs", Tabs).active = TAB_LIBRARY

    def action_tab_history(self) -> None:
        self.query_one("#main-tabs", Tabs).active = TAB_HISTORY

    def action_action_menu(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        from tui.modals.action_modal import (
            ActionModal,
            ACTION_PLAY_AUDIO, ACTION_PLAY_VIDEO,
            ACTION_DOWNLOAD_VIDEO, ACTION_DOWNLOAD_AUDIO,
            ACTION_ADD_PLAYLIST, ACTION_HIDE,
            ACTION_COPY_URL, ACTION_OPEN_BROWSER, ACTION_CHANNEL,
        )
        title = entry.get("title", "")

        def on_action(key: str | None) -> None:
            if not key:
                return
            if key == ACTION_PLAY_AUDIO:
                self.action_play_audio()
            elif key == ACTION_PLAY_VIDEO:
                self.action_play_video()
            elif key == ACTION_DOWNLOAD_VIDEO:
                self.action_download_video()
            elif key == ACTION_DOWNLOAD_AUDIO:
                self.action_download_audio()
            elif key == ACTION_ADD_PLAYLIST:
                self.action_add_playlist()
            elif key == ACTION_HIDE:
                self.action_hide_video()
            elif key == ACTION_COPY_URL:
                self.action_copy_url()
            elif key == ACTION_OPEN_BROWSER:
                self.action_open_browser()
            elif key == ACTION_CHANNEL:
                self.action_go_channel()

        self.app.push_screen(ActionModal(title), on_action)

    def action_play_audio(self) -> None:
        entry = self._get_focused_entry()
        if entry:
            self._start_audio(entry)

    def action_play_or_seek_fwd(self) -> None:
        """l key: seek +5s while playing, otherwise start audio."""
        if self._player.is_playing:
            self._player.seek(5)
        else:
            entry = self._get_focused_entry()
            if entry:
                self._start_audio(entry)

    def action_seek_fwd_large(self) -> None:
        """L key: seek +30s while playing, otherwise start audio with quality picker."""
        if self._player.is_playing:
            self._player.seek(30)
        else:
            entry = self._get_focused_entry()
            if not entry:
                return
            from tui.modals.quality_modal import QualityModal

            def on_quality(result: tuple[str, str] | None) -> None:
                fmt = result[1] if result else None
                if fmt and entry.get("id"):
                    _cache.set_last_quality(entry["id"], "audio", fmt)
                self._start_audio(entry, force_format=fmt)

            self.app.push_screen(QualityModal("audio"), on_quality)

    def action_play_video(self) -> None:
        entry = self._get_focused_entry()
        if entry:
            self._start_video(entry)

    def action_play_video_quality(self) -> None:
        """W key: always show the quality picker for video."""
        entry = self._get_focused_entry()
        if not entry:
            return
        from tui.modals.quality_modal import QualityModal

        def on_quality(result: tuple[str, str] | None) -> None:
            fmt = result[1] if result else None
            if fmt and entry.get("id"):
                _cache.set_last_quality(entry["id"], "video", fmt)
            self._start_video(entry, force_format=fmt)

        self.app.push_screen(QualityModal("video"), on_quality)

    def action_download_video(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        from tui.modals.quality_modal import QualityModal
        def on_quality(result: tuple[str, str] | None) -> None:
            fmt = result[1] if result else None
            self._open_download_modal(entry, "video", fmt)
        self.app.push_screen(QualityModal("video"), on_quality)

    def action_download_audio(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        from tui.modals.quality_modal import QualityModal
        def on_quality(result: tuple[str, str] | None) -> None:
            fmt = result[1] if result else None
            self._open_download_modal(entry, "audio", fmt)
        self.app.push_screen(QualityModal("audio"), on_quality)

    def action_add_playlist(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        from tui.modals.playlist_modal import PlaylistModal
        def on_playlist(name: str | None) -> None:
            if name and vid:
                _playlist.add_video(name, vid)
                self._show_notification(f'Added to \u201c{name}\u201d')
        self.app.push_screen(PlaylistModal(vid), on_playlist)

    def action_hide_video(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        if vid:
            _hidden.hide(vid)
            vl = self.query_one("#video-list", VideoListPanel)
            # Move cursor then reload to remove the entry
            self._show_notification("Video hidden")
            tab = self._active_tab
            self._fetch_feed(tab, self._current_page.get(tab, 1))

    def action_copy_url(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        url = f"https://www.youtube.com/watch?v={vid}"
        import subprocess
        try:
            subprocess.run(["pbcopy"], input=url.encode(), check=True)
            self._show_notification("URL copied")
        except Exception:
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=url.encode(), check=True)
                self._show_notification("URL copied")
            except Exception:
                self._show_notification(f"URL: {url}")

    def action_open_browser(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        webbrowser.open(f"https://www.youtube.com/watch?v={vid}")

    def action_go_channel(self) -> None:
        entry = self._get_focused_entry()
        if not entry:
            return
        channel_url = entry.get("channel_url") or entry.get("uploader_url") or ""
        channel = entry.get("channel") or entry.get("uploader") or ""
        if channel_url and channel:
            from tui.screens.channel_screen import ChannelScreen
            self.app.push_screen(ChannelScreen(channel_url, channel, self._config))

    # Playback controls
    def action_pause_toggle(self) -> None:
        if self._player.is_playing:
            self._player.pause_toggle()

    def action_seek_back_small(self) -> None:
        if self._player.is_playing:
            self._player.seek(-5)

    def action_seek_back_large(self) -> None:
        if self._player.is_playing:
            self._player.seek(-30)

    def action_vol_down(self) -> None:
        if self._player.is_playing:
            self._player.volume_down(self._config.volume_step)

    def action_vol_up(self) -> None:
        if self._player.is_playing:
            self._player.volume_up(self._config.volume_step)

    def _seek_pct(self, pct: int) -> None:
        if self._player.is_playing:
            self._player.seek_percent(pct)

    def action_seek_pct_0(self) -> None:
        self._seek_pct(0)

    def action_seek_pct_10(self) -> None:
        self._seek_pct(10)

    def action_seek_pct_20(self) -> None:
        self._seek_pct(20)

    def action_seek_pct_30(self) -> None:
        self._seek_pct(30)

    def action_seek_pct_40(self) -> None:
        self._seek_pct(40)

    def action_seek_pct_50(self) -> None:
        self._seek_pct(50)

    def action_seek_pct_60(self) -> None:
        self._seek_pct(60)

    def action_seek_pct_70(self) -> None:
        self._seek_pct(70)

    def action_seek_pct_80(self) -> None:
        self._seek_pct(80)

    def action_seek_pct_90(self) -> None:
        self._seek_pct(90)

    def action_stop_playback(self) -> None:
        self._player.stop()
        self._queue.clear()
        self.query_one("#mini-player", MiniPlayer).set_idle()

    def action_enqueue(self) -> None:
        """Add focused entry to the playback queue."""
        if not self._player.is_playing:
            return
        entry = self._get_focused_entry()
        if not entry:
            return
        # Don't enqueue the currently playing video
        if entry.get("id") == self._now_playing_id:
            return
        self._queue.append(entry)
        self.query_one("#mini-player", MiniPlayer).update_queue(len(self._queue))
        title = entry.get("title", "?")
        self._notify(f"Queued: {title[:40]}")

    def action_skip_next(self) -> None:
        """Skip to the next entry in the queue."""
        if not self._queue:
            self._notify("Queue is empty", "warning")
            return
        next_entry = self._queue.pop(0)
        self.query_one("#mini-player", MiniPlayer).update_queue(len(self._queue))
        if self._now_playing_mode == "VIDEO":
            self._start_video(next_entry)
        else:
            self._start_audio(next_entry)

    def action_add_bookmark(self) -> None:
        if not self._now_playing_id or not self._player.is_playing:
            return
        pos = self._player.state.position
        _history.add_bookmark(self._now_playing_id, pos)
        # Refresh MiniPlayer bookmark ticks
        bms = _history.get_bookmarks(self._now_playing_id)
        bookmark_positions = [b["position"] for b in bms]
        try:
            from tui.components.progress_bar import _fmt_time
            self.query_one("#mini-player", MiniPlayer).set_playing(
                mode=self._now_playing_mode or "AUDIO",
                title=self._player.state.title,
                channel="",
                volume=self._player.state.volume,
                bookmarks=bookmark_positions,
            )
        except Exception:
            pass
        self._notify(f"Bookmark at {_fmt_time(pos)}", "success")

    def action_jump_bookmark(self) -> None:
        if not self._now_playing_id:
            return
        from tui.modals.bookmark_modal import BookmarkModal

        def on_result(pos: float | None) -> None:
            if pos is not None and self._player.is_playing:
                self._player.seek(pos - self._player.state.position)

        self.app.push_screen(BookmarkModal(self._now_playing_id), on_result)

    # Cursor
    def action_cursor_top(self) -> None:
        self.query_one("#video-list", VideoListPanel).cursor_to_top()

    def action_cursor_bottom(self) -> None:
        self.query_one("#video-list", VideoListPanel).cursor_to_bottom()

    def action_cursor_down(self) -> None:
        self.query_one("#video-list", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#video-list", VideoListPanel).cursor_up()

    def action_page_next(self) -> None:
        """J: Next page."""
        tab = self._active_tab
        page = self._current_page.get(tab, 1) + 1
        total = self._total_pages.get(tab, 1)
        if page <= total:
            self._fetch_feed(tab, page)

    def action_page_prev(self) -> None:
        """K: Previous page."""
        tab = self._active_tab
        page = self._current_page.get(tab, 1) - 1
        if page >= 1:
            self._fetch_feed(tab, page)

    def action_toggle_debug(self) -> None:
        """Ctrl+D: Toggle debug log panel."""
        try:
            import logger as _logger
            _logger.toggle_debug()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_focused_entry(self) -> dict | None:
        vl = self.query_one("#video-list", VideoListPanel)
        entry = vl.cursor_entry()
        if entry:
            return entry
        return self._focused_entry

    def _show_error(self, title: str, message: str) -> None:
        from tui.modals.error_modal import ErrorModal
        self.app.push_screen(ErrorModal(title, message))

    def on_notification_bar_open_error_requested(self, event: NotificationBar.OpenErrorRequested) -> None:
        self._show_error(event.title, event.detail)

    def _notify(self, text: str, kind: str = "info") -> None:
        """Show an ephemeral notification in the NotificationBar."""
        try:
            self.query_one("#notify-bar", NotificationBar).show(text, kind=kind)
        except Exception:
            pass

    def _notify_error(self, text: str, detail: str = "") -> None:
        """Show a persistent error notification."""
        try:
            self.query_one("#notify-bar", NotificationBar).show_error(text, detail)
        except Exception:
            pass

    def _show_notification(self, text: str) -> None:
        self._notify(text)
