"""MainScreen — primary TUI screen with nav tabs, video list, and detail panel."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections import OrderedDict
from datetime import datetime

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, ListView, RichLog, Static, Tab, Tabs

from src import logger as _logger
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

# How many entries to fetch per batch (4 pages of 20).
_BATCH_FETCH_COUNT = 80
_PAGE_SIZE = 20

# ── Custom Header ─────────────────────────────────────────────────────────────


class AppHeader(Widget):
    """Modern custom header: Clock (Left), Title (Center), Animated Status (Right)."""

    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = "IDLE"
        self._frame = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-layout"):
            yield Static("", id="header-clock")
            yield Static("📺 TermTube", id="header-title")
            yield Static("", id="header-status")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._update_clock)
        self.set_interval(0.1, self._animate_spinner)
        self._update_clock()

    def _update_clock(self) -> None:
        now = datetime.now().strftime("%I:%M %p")
        self.query_one("#header-clock", Static).update(f"[dim]⌚ {now}[/dim]")

    def _animate_spinner(self) -> None:
        if self._state != "LOADING":
            return
        char = self._SPINNER[self._frame % len(self._SPINNER)]
        self.query_one("#header-status", Static).update(char)
        self._frame += 1

    def set_status_loading(self) -> None:
        self._state = "LOADING"
        self._frame = 0
        char = self._SPINNER[0]
        self.query_one("#header-status", Static).update(char)

    def set_status_idle(self) -> None:
        self._state = "IDLE"
        self.query_one("#header-status", Static).update("")

    def set_status_error(self) -> None:
        self._state = "ERROR"
        self.query_one("#header-status", Static).update("✗")


# ── Helpers ───────────────────────────────────────────────────────────────────


from src.tui.fmt import fmt_age_seconds as _fmt_age_seconds


# ── Tab definitions ────────────────────────────────────────────────────────────

_TABS = [
    ("home", "🏠 Home"),
    ("subscriptions", "📺 Subscriptions"),
    ("search", "🔍 Search"),
    ("history", "🕐 History"),
    ("library", "📁 Library"),
    ("playlists", "🎵 Playlists"),
    ("help", "📚 Help"),
]

_AUDIO_SOCKET = None  # Lazy-initialized from platform module


def _get_audio_socket() -> str:
    global _AUDIO_SOCKET
    if _AUDIO_SOCKET is None:
        from src.platform import get_audio_ipc_path
        _AUDIO_SOCKET = get_audio_ipc_path()
    return _AUDIO_SOCKET

# ── Dwell / freshness tuning ──────────────────────────────────────────────────
_FOCUS_DWELL_S = 0.10
_THUMB_DWELL_S = 0.15
_FRESHNESS_REFRESH_S = 60.0
_FEED_TABS = ("home",)
_PAGED_TABS = ("home", "search")
_CHANNEL_TABS = ("subscriptions",)
_CHAFA_RAM_CACHE_MAX = 64


class MainScreen(Screen):
    """
    Primary screen. Manages:
      • Nav tabs + streaming video feeds (left panel)
      • Detail panel with thumbnail, metadata, embedded audio player (right panel)
      • Audio playback state — mpv runs in background, never blocks the TUI
      • Video playback via WatchModal for seamless progress tracking
    """

    BINDINGS = [
        # List navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "page_first", "First Page", show=False),
        Binding("G", "page_last", "Last Page", show=False),
        Binding("left_square_bracket", "page_prev", "Prev Page", show=False),
        Binding("right_square_bracket", "page_next", "Next Page", show=False),
        Binding("left", "page_prev", "Prev Page", show=False),
        Binding("right", "page_next", "Next Page", show=False),
        Binding("backspace", "nav_back", "Back", show=False),
        # Enter → video action menu
        Binding("enter", "activate", "Actions", show=False),
        # Playback (direct shortcuts, bypass action menu)
        Binding("w", "watch", "Watch", show=False),
        Binding("W", "watch_quality", "Quality ▶", show=False),
        # l / L / h / H — context-aware: seek when audio playing, else listen/nothing
        Binding("l", "listen_or_seek", "Listen", show=False),
        Binding("L", "listen_q_or_seek_big", "Quality ♪", show=False),
        Binding("h", "audio_seek_back", show=False),
        Binding("H", "audio_seek_back_big", show=False),
        Binding("space", "audio_pause", "Pause", show=False),
        Binding("s", "audio_stop_or_subscribe", show=False),
        # 0-9 audio seek
        Binding("0", "audio_pct_0", show=False),
        Binding("1", "audio_pct_10", show=False),
        Binding("2", "audio_pct_20", show=False),
        Binding("3", "audio_pct_30", show=False),
        Binding("4", "audio_pct_40", show=False),
        Binding("5", "audio_pct_50", show=False),
        Binding("6", "audio_pct_60", show=False),
        Binding("7", "audio_pct_70", show=False),
        Binding("8", "audio_pct_80", show=False),
        Binding("9", "audio_pct_90", show=False),
        # Download
        Binding("d", "download", "Download", show=False),
        Binding("c", "channel", "Channel", show=False),
        # Queue
        Binding("e", "queue_audio", "Queue", show=False),
        Binding(">", "audio_skip", "Skip", show=False),
        # Copy URL
        Binding("y", "copy_url", "Copy URL", show=False),
        # Other
        Binding("p", "playlist", "Playlist", show=False),
        Binding("b", "browser", "Browser", show=False),
        # App Footer visible commands
        Binding("/", "search", "Search", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("comma", "settings", "Settings", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        Binding("?", "toggle_help", "Help", show=True),
        Binding("ctrl+d", "toggle_log", "Debug", show=False),
        # Page shortcuts — F1-F7
        Binding("f1", "tab_home", show=False),
        Binding("f2", "tab_subs", show=False),
        Binding("f3", "tab_search", show=False),
        Binding("f4", "tab_history", show=False),
        Binding("f5", "tab_library", show=False),
        Binding("f6", "tab_playlists", show=False),
        Binding("f7", "tab_help", show=False),
        # Nav picker
        Binding("grave_accent", "nav_picker", "Pages", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_tab = ""
        self._search_query: str = ""
        self._nav_stack: list[str] = []
        self._log_visible = False
        self._activating_search_programmatically: bool = False
        # ── Audio player state ────────────────────────────────────────────────
        self._audio_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._audio_entry: dict | None = None
        self._audio_stopped = False
        self._audio_poll_timer = None
        self._audio_queue: list[dict] = []
        self._audio_session: int = 0
        self._sb_segments: list = []
        self._sb_skipped: set[int] = set()
        # ── Focus / thumbnail dwell-driven workers ────────────────────────────
        self._focus_dwell_timer: Timer | None = None
        self._thumb_dwell_timer: Timer | None = None
        self._focus_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._thumb_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._focus_session: int = 0
        self._thumb_session: int = 0
        self._last_focus_id: str = ""
        # Prefetched direct stream URLs keyed by video ID
        self._stream_urls: dict[str, dict] = {}
        self._stream_url_ready: dict[str, threading.Event] = {}
        self._stream_url_session: int = 0
        self._stream_url_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        # In-RAM LRU of rendered chafa output keyed by (vid, cols, rows, fmt).
        self._chafa_ram_cache: OrderedDict[tuple[str, int, int, str], str] = OrderedDict()
        # ── Feed loading state (paged) ────────────────────────────────────────
        self._home_loading: bool = False
        self._freshness_timer: Timer | None = None
        # Active workers reference counter for honest header spinner.
        self._active_workers: int = 0

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Tabs(
            *[Tab(label, id=tid) for tid, label in _TABS],
            id="nav-tabs",
        )
        with Horizontal(id="main-content"):
            yield VideoListPanel(id="video-list-panel")
            yield DetailPanel(id="detail-panel")
        yield RichLog(
            id="debug-log", highlight=True, markup=True, max_lines=100, wrap=False
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#debug-log").display = False
        # Prevent the Tabs widget from stealing focus during DOM mutations.
        tabs = self.query_one("#nav-tabs", Tabs)
        tabs.can_focus = False
        for tab in tabs.query(Tab):
            tab.can_focus = False
        if _logger.is_debug():
            _logger.register_tui_sink(self._on_log_record)
            _logger.info("MainScreen mounted; debug log wired to TUI sink")
            self._log(f"[green]Debug logging active[/green] — file: [dim]{_logger.log_file()}[/dim]")
        # Periodic freshness label refresh ("updated 4m ago").
        self._freshness_timer = self.set_interval(_FRESHNESS_REFRESH_S, self._update_freshness_label)
        self.call_after_refresh(self._maybe_show_warnings)
        # Check for a yt-dlp version change after a background update.
        # Runs in a worker thread so the --version subprocess doesn't block the loop.
        self.set_timer(0.8, self._check_update_notification)

    @work(thread=True)
    def _check_update_notification(self) -> None:
        """Run in background: detect yt-dlp version change and notify if updated."""
        try:
            from src.updater import check_for_update_notification
            msg = check_for_update_notification()
            if msg:
                self.app.call_from_thread(self.notify, msg, timeout=6)
        except Exception:
            pass

    def _maybe_show_warnings(self) -> None:
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        need_image_warning = (
            not _HAS_TEXTUAL_IMAGE
            and not self.app.config.get("thumbnail_warning_dismissed", False)
        )

        if need_image_warning:
            from src.tui.screens.image_warning_modal import ImageWarningModal

            def _on_image_done(never_show: bool) -> None:
                if never_show:
                    self.app.config._data["thumbnail_warning_dismissed"] = True
                    self.app.config.save()
                self._maybe_show_cookie_warning()

            self.app.push_screen(ImageWarningModal(), _on_image_done)
        else:
            self._maybe_show_cookie_warning()

    def _maybe_show_cookie_warning(self) -> None:
        config = self.app.config
        if config.cookies_file_path and config.cookies_file_path.exists():
            return
        if config.get("cookie_warning_dismissed", False):
            return

        from src.tui.screens.cookie_warning_modal import CookieWarningModal

        def _on_cookie_done(choice: str) -> None:
            if choice == "cookiewarn-now":
                self._run_cookie_refresh_now()
            elif choice == "cookiewarn-exit":
                self.app._refresh_cookies_on_exit = True  # type: ignore[attr-defined]
            elif choice == "cookiewarn-never":
                config._data["cookie_warning_dismissed"] = True
                config.save()

        self.app.push_screen(CookieWarningModal(), _on_cookie_done)

    @work(thread=True)
    def _run_cookie_refresh_now(self) -> None:
        from src.updater import refresh_cookies
        success = refresh_cookies(self.app.config, verbose=False)
        if success:
            self.app.call_from_thread(
                self.notify, "Cookies refreshed successfully.", timeout=5
            )
        else:
            self.app.call_from_thread(
                self.notify, "Cookie refresh failed. Try: termtube --refresh-cookies",
                severity="error", timeout=6,
            )

    # ── Focus guard ───────────────────────────────────────────────────────────

    def on_key(self) -> None:
        """Ensure focus stays on the video list during normal browsing.

        Textual can drift focus to the Tabs widget when the ListView DOM is
        mutated (clear/append). If focus has escaped to anything other than the
        list, reclaim it so keystrokes work as expected.
        """
        focused = self.app.focused
        if focused is None or not isinstance(focused, ListView):
            try:
                self.query_one("#video-list-panel", VideoListPanel)._lv.focus()
            except Exception:
                pass

    # ── Tab switching ─────────────────────────────────────────────────────────

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if not event.tab or not event.tab.id:
            return
        tab_id = event.tab.id
        # Guard: Textual fires spurious TabActivated events when ListView DOM
        # mutations (appending new items) shift focus to the Tabs widget.
        # If the activated tab is already the current one, this is always a
        # false positive — discard it silently. Genuine tab switches always
        # produce a different tab_id from the current one.
        if tab_id == self._current_tab:
            return
        _logger.info("page switch → %s", tab_id)
        self._cancel_pending_focus_and_thumb()
        if tab_id == "search":
            if self._activating_search_programmatically:
                self._activating_search_programmatically = False
            elif self._current_tab == "search" and self._search_query:
                pass
            else:
                self._open_search_dialog()
        elif tab_id == "help":
            prev_tab = self._current_tab
            tabs = self.query_one("#nav-tabs", Tabs)

            def _after_help(_: None) -> None:
                tabs.active = prev_tab if prev_tab != "help" else "home"

            self.app.push_screen(
                __import__(
                    "src.tui.screens.help_screen", fromlist=["HelpScreen"]
                ).HelpScreen(),
                _after_help,
            )
        else:
            # Save stash when leaving a feed tab so next boot is instant.
            if self._current_tab in _FEED_TABS:
                self._save_feed_stash(self._current_tab)
            self._current_tab = tab_id
            self._nav_stack.clear()
            self._load_view(tab_id)

    def _save_feed_stash(self, feed_key: str) -> None:
        """Persist the first unseen page (up to 20 entries) to disk.

        Saves entries from pages the user hasn't navigated to. If fewer than
        PAGE_SIZE entries are unseen, backfills from earlier pages so the stash
        is always exactly 20 entries (the user never sees a partial first page).
        """
        if feed_key != "home":
            return
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
            unseen = panel.all_unseen_entries()
            if len(unseen) < _PAGE_SIZE:
                # Backfill: grab from earlier pages the user HAS visited (tail end)
                all_entries: list[dict] = []
                for pn in sorted(panel._pages.keys()):
                    all_entries.extend(panel._pages[pn])
                needed = _PAGE_SIZE - len(unseen)
                backfill = all_entries[-(needed):] if len(all_entries) >= needed else all_entries
                # Deduplicate: unseen entries take priority
                seen_ids = {e.get("id") for e in unseen}
                for e in backfill:
                    if e.get("id") not in seen_ids:
                        unseen.append(e)
                    if len(unseen) >= _PAGE_SIZE:
                        break
            stash_entries = unseen[:_PAGE_SIZE]
            if stash_entries:
                self.app.cache.put_home_stash(stash_entries)
                _logger.debug("stash: saved %d entries", len(stash_entries))
        except Exception as exc:
            _logger.debug("stash save error: %s", exc)

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        self.query_one("#detail-panel", DetailPanel).clear()
        if view not in _CHANNEL_TABS:
            try:
                self.query_one("#detail-panel", DetailPanel).set_video_mode()
            except Exception: pass
        # Track whether a feed loader is running so the TabActivated guard works.
        self._home_loading = (view in _FEED_TABS)
        self._stream_view(view)

    # ── Paged feed workers ──────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str) -> None:
        """Background worker: dispatch loading for any tab view."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        config = self.app.config
        cache = self.app.cache

        self._worker_start()
        try:
            if view in _FEED_TABS:
                self._load_feed_paged(view, panel, config, cache)
            elif view in _CHANNEL_TABS:
                self._load_subscriptions_channels(panel, config, cache)
            elif view == "search":
                if not self._search_query:
                    self.app.call_from_thread(
                        panel.set_empty_message, "Press / to search"
                    )
                    return
                self._load_search_paged(panel, config, cache)
            elif view == "history":
                from src import history as hist
                entries = list(hist.iter_entries())
                self._load_simple_list(panel, entries)
            elif view == "library":
                from src import library as lib
                entries = list(lib.all_entries(config.video_dir, config.audio_dir))
                self._load_simple_list(panel, entries)
            elif view == "playlists":
                self._load_playlists_sync(panel)
            elif view.startswith("playlist:"):
                self._load_playlist_videos_sync(view[len("playlist:"):], panel, cache)
        except Exception as exc:
            msg = str(exc)
            self.app.call_from_thread(panel.set_error_message, f"⚠ {msg}")
            self.app.call_from_thread(self._log, f"[red]Error in {view}: {msg}[/red]")
        finally:
            self._home_loading = False
            self._worker_end()
            if view in _FEED_TABS:
                self.app.call_from_thread(self._update_freshness_label)

    def _load_feed_paged(self, feed_key: str, panel, config, cache) -> None:
        """Home / subscriptions paged feed loader.

        Boot sequence:
          1. If a stash exists, show it as page 1 instantly.
          2. Fetch _BATCH_FETCH_COUNT fresh entries from yt-dlp.
          3. Split into pages of _PAGE_SIZE and store them.
          4. Prefetch metadata for the first entry of page 2.
        """
        import src.ytdlp as ytdlp

        is_suppressed = cache.is_suppressed

        # Step 1 — stash (home only): show instantly as page 1
        stash_loaded = False
        stash_ids: set[str] = set()
        if feed_key == "home":
            stash = cache.get_home_stash()
            if stash:
                filtered = [e for e in stash if not is_suppressed(e.get("id", ""))]
                if filtered:
                    stash_ids = {e.get("id", "") for e in filtered if e.get("id")}
                    self.app.call_from_thread(panel.add_page, 1, filtered)
                    self.app.call_from_thread(panel.load_page, 1)
                    stash_loaded = True
                    _logger.debug("feed %s: loaded %d stash entries as page 1", feed_key, len(filtered))

        # Step 2 — fresh fetch (skip stash IDs to avoid duplicates)
        skip_ids = stash_ids if stash_loaded else set()
        entries = ytdlp.fetch_page_batch(
            ytdlp.FEED_URLS[feed_key],
            config,
            cache,
            skip_ids=skip_ids,
            count=_BATCH_FETCH_COUNT,
            feed_key=feed_key,
        )

        # Filter suppressed
        if feed_key == "home":
            entries = [e for e in entries if not is_suppressed(e.get("id", ""))]

        # Step 3 — split into pages (don't touch page 1 if stash is showing)
        if not entries and not stash_loaded:
            self.app.call_from_thread(
                panel.set_error_message,
                "⚠ Home feed returned no results.\n\n"
                "Your yt-dlp version may be outdated. Run:\n"
                "  termtube --update",
            )
            return

        start_page = 2 if stash_loaded else 1
        for i in range(0, len(entries), _PAGE_SIZE):
            page_num = start_page + (i // _PAGE_SIZE)
            page_entries = entries[i:i + _PAGE_SIZE]
            self.app.call_from_thread(panel.add_page, page_num, page_entries)

        # Show page 1 if we didn't have a stash
        if not stash_loaded:
            self.app.call_from_thread(panel.load_page, 1)

        self.app.call_from_thread(panel.finish_loading)

        # Step 4 — schedule prefetch on the focus worker (keeps feed_loader clean)
        self.app.call_from_thread(self._schedule_prefetch)

        # Prune cache to cap
        try:
            cache.prune_video_cache_fifo(100)
        except Exception:
            pass

    def _load_subscriptions_channels(self, panel, config, cache) -> None:
        import src.ytdlp as ytdlp
        entries = ytdlp.fetch_subscribed_channels(config, cache)
        if not entries:
            self.app.call_from_thread(panel.set_empty_message, "No subscriptions found.")
            return
        self.app.call_from_thread(self._apply_channel_mode_to_detail)
        for i in range(0, len(entries), _PAGE_SIZE):
            page_num = 1 + int(i / _PAGE_SIZE)
            page_entries = entries[i:i + _PAGE_SIZE]
            self.app.call_from_thread(panel.add_page, page_num, page_entries)
        self.app.call_from_thread(panel.load_page, 1)
        self.app.call_from_thread(panel.finish_loading)

    def _apply_channel_mode_to_detail(self) -> None:
        try:
            dp = self.query_one("#detail-panel", DetailPanel)
            dp.set_channel_mode()
        except Exception: pass

    def _load_search_paged(self, panel, config, cache) -> None:
        """Paged search results loader."""
        import src.ytdlp as ytdlp

        entries = ytdlp.fetch_search_batch(
            self._search_query, config, cache, count=50
        )

        # Split into pages of _PAGE_SIZE
        for i in range(0, len(entries), _PAGE_SIZE):
            page_num = 1 + (i // _PAGE_SIZE)
            page_entries = entries[i:i + _PAGE_SIZE]
            self.app.call_from_thread(panel.add_page, page_num, page_entries)

        self.app.call_from_thread(panel.load_page, 1)
        self.app.call_from_thread(panel.finish_loading)

    def _load_simple_list(self, panel, entries: list[dict]) -> None:
        """Load a simple (non-paged) list for history/library tabs."""
        if not entries:
            self.app.call_from_thread(panel.set_empty_message, "No items")
            return
        # Put all entries into page 1 (no pagination for local data)
        self.app.call_from_thread(panel.add_page, 1, entries)
        self.app.call_from_thread(panel.load_page, 1)
        self.app.call_from_thread(panel.finish_loading)

    def _schedule_prefetch(self) -> None:
        """Schedule a prefetch of the next page's first entry on the focus worker."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        next_page = panel.current_page + 1
        entries = panel.page_entries(next_page)
        if not entries:
            return
        first_entry = entries[0]
        vid = first_entry.get("id", "")
        if not vid or vid.startswith("__"):
            return
        cached = self.app.cache.get_video(vid)
        if cached and cached.get("description") is not None:
            return
        self._focus_session += 1
        session = self._focus_session
        self._focus_worker(vid, first_entry, session)

    @work(thread=True, exclusive=True, group="feed_loader")
    def _fetch_more_pages(self) -> None:
        """Fetch the next batch of pages when user navigates to a non-existent page."""
        import src.ytdlp as ytdlp

        panel = self.query_one("#video-list-panel", VideoListPanel)
        config = self.app.config
        cache = self.app.cache

        tab = self._current_tab
        if tab not in _PAGED_TABS:
            return

        self.app.call_from_thread(panel.show_next_page_loading)
        self._worker_start()
        try:
            skip_ids = set(panel._seen_ids)
            start_page = panel.current_page

            if tab in _FEED_TABS:
                url = ytdlp.FEED_URLS[tab]
                entries = ytdlp.fetch_page_batch(
                    url, config, cache,
                    skip_ids=skip_ids,
                    count=_BATCH_FETCH_COUNT,
                    feed_key=None,
                        )
                if tab == "home":
                    is_suppressed = cache.is_suppressed
                    entries = [e for e in entries if not is_suppressed(e.get("id", ""))]
            elif tab == "search" and self._search_query:
                entries = ytdlp.fetch_search_batch(
                    self._search_query, config, cache,
                    skip_ids=skip_ids,
                    count=50,
                )
            else:
                return

            if not entries:
                self.app.call_from_thread(panel.finish_loading)
                return

            for i in range(0, len(entries), _PAGE_SIZE):
                page_num = start_page + (i // _PAGE_SIZE)
                page_entries = entries[i:i + _PAGE_SIZE]
                self.app.call_from_thread(panel.add_page, page_num, page_entries)

            self.app.call_from_thread(panel.load_page, start_page)

        except Exception as exc:
            _logger.debug("fetch_more_pages error: %s", exc)
            self.app.call_from_thread(panel.finish_loading)
        finally:
            self._worker_end()

    @work(thread=True, exclusive=True, group="feed_loader")
    def _prefetch_more_pages(self) -> None:
        """Proactively fetch next batch when user lands on the last page."""
        import src.ytdlp as ytdlp

        panel = self.query_one("#video-list-panel", VideoListPanel)
        config = self.app.config
        cache = self.app.cache

        tab = self._current_tab
        if tab not in _PAGED_TABS:
            return

        self._worker_start()
        try:
            skip_ids = set(panel._seen_ids)
            start_page = panel.total_pages + 1

            if tab in _FEED_TABS:
                url = ytdlp.FEED_URLS[tab]
                entries = ytdlp.fetch_page_batch(
                    url, config, cache,
                    skip_ids=skip_ids,
                    count=_BATCH_FETCH_COUNT,
                    feed_key=None,
                        )
                if tab == "home":
                    is_suppressed = cache.is_suppressed
                    entries = [e for e in entries if not is_suppressed(e.get("id", ""))]
            elif tab == "search" and self._search_query:
                entries = ytdlp.fetch_search_batch(
                    self._search_query, config, cache,
                    skip_ids=skip_ids,
                    count=50,
                )
            else:
                return

            if not entries:
                return

            for i in range(0, len(entries), _PAGE_SIZE):
                page_num = start_page + (i // _PAGE_SIZE)
                page_entries = entries[i:i + _PAGE_SIZE]
                self.app.call_from_thread(panel.add_page, page_num, page_entries)

        except Exception as exc:
            _logger.debug("prefetch_more_pages error: %s", exc)
        finally:
            self._worker_end()

    def _load_playlists_sync(self, panel) -> None:
        from src import playlist

        names = playlist.list_names()
        if not names:
            self.app.call_from_thread(
                panel.set_empty_message, "No playlists. Select a video and press p."
            )
            return
        entries = []
        for name in names:
            ids = playlist.get_playlist(name)
            entry = {
                "id": f"__playlist__{name}",
                "title": f"🎵  {name}",
                "uploader": f"{len(ids)} video{'s' if len(ids)!=1 else ''}",
                "duration": None,
                "view_count": None,
                "_is_playlist": True,
                "_playlist_name": name,
            }
            entries.append(entry)
        self.app.call_from_thread(panel.add_page, 1, entries)
        self.app.call_from_thread(panel.load_page, 1)
        self.app.call_from_thread(panel.finish_loading)

    def _load_playlist_videos_sync(self, name: str, panel, cache) -> None:
        from src import playlist

        ids = playlist.get_playlist(name)
        if not ids:
            self.app.call_from_thread(
                panel.set_empty_message, f'Playlist "{name}" is empty.'
            )
            return
        entries = []
        for vid_id in ids:
            entry = cache.get_video_raw(vid_id) or {
                "id": vid_id,
                "title": vid_id,
                "uploader": "",
            }
            entries.append(entry)
        self.app.call_from_thread(panel.add_page, 1, entries)
        self.app.call_from_thread(panel.load_page, 1)
        self.app.call_from_thread(panel.finish_loading)

    # ── Detail panel events ───────────────────────────────────────────────────

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        entry = message.entry
        vid = entry.get("id", "")
        detail = self.query_one("#detail-panel", DetailPanel)
        if entry.get("_is_channel"):
            detail.update_channel_entry(entry)
            self._cancel_pending_focus_and_thumb()
            self._last_focus_id = vid
            self._kick_channel_info(vid, entry)
            return
        detail.update_basic(entry)
        self._cancel_pending_focus_and_thumb()
        self._last_focus_id = vid
        if vid and not vid.startswith("__"):
            detail.set_thumbnail_video_id(vid)
            from src.ui.thumbnail import _thumb_path
            if not _thumb_path(vid).exists():
                detail.set_thumbnail_loading()
        elif vid:
            detail.set_thumbnail_video_id(vid)
            detail.set_thumbnail_loading()
        if vid and not vid.startswith("__"):
            self._thumb_dwell_timer = self.set_timer(
                _THUMB_DWELL_S, lambda: self._kick_thumb(vid, entry)
            )
            self._focus_dwell_timer = self.set_timer(
                _FOCUS_DWELL_S, lambda: self._kick_focus(vid, entry)
            )
        self._refresh_queue_hint(entry)

    def on_detail_panel_rerender_requested(
        self, message: DetailPanel.RerenderRequested
    ) -> None:
        """Re-render the thumbnail when the panel resizes or screen resumes."""
        entry = message.entry
        vid = entry.get("id", "")
        if vid and not vid.startswith("__"):
            self._kick_thumb(vid, entry)

    def on_detail_panel_channel_clicked(
        self, message: DetailPanel.ChannelClicked
    ) -> None:
        """Open the channel screen when the channel name is clicked."""
        self._open_channel(message.entry)

    def _refresh_queue_hint(self, focused_entry: dict | None = None) -> None:
        """Update the action bar's queue hint based on what video is focused."""
        try:
            ab = self._action_bar()
        except Exception:
            return
        if focused_entry is None:
            focused_entry = self._selected_entry()
        focused_id = focused_entry.get("id") if focused_entry else None
        playing_id = self._audio_entry.get("id") if self._audio_entry else None
        queued_ids = {e.get("id") for e in self._audio_queue}
        hide_e = bool(
            focused_id and (focused_id == playing_id or focused_id in queued_ids)
        )
        ab.update_queue_hint(len(self._audio_queue), hide_e=hide_e)

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()

    # ── Focus / thumbnail dwell-driven workers ────────────────────────────────

    def _cancel_pending_focus_and_thumb(self) -> None:
        """Cancel pending dwell timers and best-effort kill in-flight subprocesses."""
        if self._focus_dwell_timer is not None:
            self._focus_dwell_timer.stop()
            self._focus_dwell_timer = None
        if self._thumb_dwell_timer is not None:
            self._thumb_dwell_timer.stop()
            self._thumb_dwell_timer = None
        # Bump session counters so any worker that already started bails on apply.
        self._focus_session += 1
        self._thumb_session += 1
        self._stream_url_session += 1
        # Best-effort kill of any subprocess still running.
        for attr in ("_focus_proc", "_thumb_proc", "_stream_url_proc"):
            proc = getattr(self, attr, None)
            if proc is None:
                continue
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            setattr(self, attr, None)

    def _kick_thumb(self, vid: str, entry: dict) -> None:
        """Dwell timer fired — actually start the thumbnail render worker."""
        self._thumb_dwell_timer = None
        if self.query_one("#detail-panel", DetailPanel).current_id != vid:
            return  # cursor moved during the timer's pre-fire scheduling slot
        self._thumb_session += 1
        session = self._thumb_session
        self._thumb_worker(vid, entry, session)

    def _kick_focus(self, vid: str, entry: dict) -> None:
        """Dwell timer fired — actually start the metadata fetch worker."""
        self._focus_dwell_timer = None
        if self.query_one("#detail-panel", DetailPanel).current_id != vid:
            return
        # Skip enrichment if we already have a description cached.
        if entry.get("description"):
            return
        self._focus_session += 1
        session = self._focus_session
        self._focus_worker(vid, entry, session)
        # Start stream URL prefetch in parallel (not after focus_worker)
        if not entry.get("_local_path") and vid:
            self._stream_url_session += 1
            event = threading.Event()
            self._stream_url_ready[vid] = event
            self._stream_url_worker(vid, self._stream_url_session)

    def _kick_channel_info(self, vid: str, entry: dict) -> None:
        if not vid or not entry.get("_is_channel"):
            return
        if not entry.get("description"):
            self._channel_info_worker(vid, entry)

    @work(thread=True, exclusive=True, group="ch_focus")
    def _channel_info_worker(self, vid: str, entry: dict) -> None:
        import src.ytdlp as ytdlp
        self._worker_start()
        try:
            url = entry.get("channel_url") or entry.get("uploader_url") or ""
            if not url: return
            info = ytdlp.fetch_channel_info(url, self.app.config, self.app.cache)
            if info and info.get("id") == vid or True:
                self.app.call_from_thread(self._apply_ch_info_to_detail, vid, info)
        except Exception as exc:
            _logger.debug("ch_info_worker exc: %s", exc)
        finally:
            self._worker_end()

    def _apply_ch_info_to_detail(self, vid: str, info: dict | None) -> None:
        if info is None: return
        try:
            dp = self.query_one("#detail-panel", DetailPanel)
            if dp.current_id != vid: return
            merged = {**dp.last_entry, **info} if dp.last_entry else info
            dp.update_channel_entry(merged)
        except Exception: pass

    @work(thread=True, exclusive=True, group="focus")
    def _focus_worker(self, vid: str, entry: dict, session: int) -> None:
        """Fetch full metadata for vid and apply to UI. Latest-wins via session.
        Cancel-before-start: the session counter + proc.terminate() ensures
        only 1 metadata worker exists at any time.
        """
        import src.ytdlp as ytdlp

        self._worker_start()

        def _on_proc(p: subprocess.Popen) -> None:
            self._focus_proc = p

        try:
            full = ytdlp.fetch_full(
                vid, self.app.config, self.app.cache, on_proc_started=_on_proc
            )
        except Exception as exc:
            _logger.debug("focus_worker error for %s: %s", vid, exc)
            return
        finally:
            self._focus_proc = None
            self._worker_end()

        if full is None or session != self._focus_session:
            return
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
            self.app.call_from_thread(panel.update_entry_by_id, vid, full)
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).refresh_metadata, full
            )
        except Exception:
            pass

    @work(thread=True, exclusive=True, group="stream_prefetch")
    def _stream_url_worker(self, vid: str, session: int) -> None:
        """Prefetch direct audio/video stream URLs for faster playback start."""
        import src.ytdlp as ytdlp

        if session != self._stream_url_session:
            self._signal_stream_ready(vid)
            return

        def _on_proc(p: subprocess.Popen) -> None:
            self._stream_url_proc = p

        try:
            result = ytdlp.fetch_stream_urls(
                vid, self.app.config, on_proc_started=_on_proc
            )
        except Exception as exc:
            _logger.debug("stream_url_worker error for %s: %s", vid, exc)
            self._signal_stream_ready(vid)
            return
        finally:
            self._stream_url_proc = None

        if result is None or session != self._stream_url_session:
            self._signal_stream_ready(vid)
            return
        self._stream_urls[vid] = result
        _logger.debug("stream_url_worker: prefetched URLs for %s", vid)
        self._signal_stream_ready(vid)

    def _signal_stream_ready(self, vid: str) -> None:
        """Signal that stream URL prefetch is complete (success or failure)."""
        event = self._stream_url_ready.get(vid)
        if event:
            event.set()

    @work(thread=True, exclusive=True, group="thumb")
    def _thumb_worker(self, vid: str, entry: dict, session: int) -> None:
        """Render and apply a thumbnail. Two paths:

          • textual-image available → ensure JPEG on disk, hand path to widget.
          • else → chafa render with (vid, cols, rows) cache, hand ANSI to widget.

        Both paths are latest-wins via session counter and best-effort cancel
        the previous chafa subprocess.
        """
        from src.ui import thumbnail as thumb_mod
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        detail = self.query_one("#detail-panel", DetailPanel)

        if _HAS_TEXTUAL_IMAGE:
            local = thumb_mod._thumb_path(vid)
            if not local.exists():
                url = thumb_mod._best_thumb_url(entry)
                if url:
                    local = thumb_mod.download(vid, url) or local
            if session != self._thumb_session:
                return
            if local and local.exists():
                # Validate the JPEG fully in this thread before handing to
                # textual-image — avoids a noisy OSError deep in PIL.
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(local) as _pil_img:
                        _pil_img.load()
                except Exception:
                    self.app.call_from_thread(detail.set_thumbnail_placeholder)
                    return
                if session != self._thumb_session:
                    return
                self.app.call_from_thread(detail.set_thumbnail_image, vid, local)
            else:
                self.app.call_from_thread(detail.set_thumbnail_placeholder)
            return

        # ── chafa branch ─────────────────────────────────────────────────────
        try:
            thumb_widget = detail.query_one("#thumbnail")
            cols = thumb_widget.size.width if thumb_widget.size.width > 0 else max(30, (detail.size.width or 80) - 4)
            rows = thumb_widget.size.height if thumb_widget.size.height > 0 else 25
        except Exception:
            cols, rows = 38, 20

        config = getattr(self.app, "config", None)
        fmt = thumb_mod._chafa_format_for_tui(config)
        cache_key_fmt = "ascii" if fmt == "ascii" else "symbols"
        ram_key = (vid, cols, rows, cache_key_fmt)

        # RAM cache hit — instant.
        ansi = self._chafa_ram_cache.get(ram_key)
        if ansi is not None:
            self._chafa_ram_cache.move_to_end(ram_key)
            self.app.call_from_thread(detail.set_thumbnail_ansi, vid, ansi)
            return

        def _on_chafa_proc(p: subprocess.Popen) -> None:
            self._thumb_proc = p

        try:
            ansi = thumb_mod.render(
                vid, entry, cols=cols, rows=rows, config=config,
                on_proc_started=_on_chafa_proc,
            )
        finally:
            self._thumb_proc = None

        if session != self._thumb_session:
            return

        if ansi:
            self._chafa_ram_cache[ram_key] = ansi
            if len(self._chafa_ram_cache) > _CHAFA_RAM_CACHE_MAX:
                self._chafa_ram_cache.popitem(last=False)
            self.app.call_from_thread(detail.set_thumbnail_ansi, vid, ansi)
        else:
            self.app.call_from_thread(detail.set_thumbnail_placeholder)

    # ── Worker reference counter (honest spinner) ──────────────────────────────

    def _worker_start(self) -> None:
        """Increment active worker count and show spinner."""
        self._active_workers += 1
        try:
            self.app.call_from_thread(self.query_one(AppHeader).set_status_loading)
        except Exception:
            pass

    def _worker_end(self) -> None:
        """Decrement active worker count; hide spinner when all done."""
        self._active_workers = max(0, self._active_workers - 1)
        if self._active_workers == 0:
            try:
                self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)
            except Exception:
                pass

    # ── Freshness label / stale-cache refresh ─────────────────────────────────

    def _update_freshness_label(self) -> None:
        """Refresh the 'updated Nm ago · R to refresh' header on the list panel."""
        if self._current_tab not in _FEED_TABS:
            try:
                self.query_one("#video-list-panel", VideoListPanel).set_freshness("")
            except Exception:
                pass
            return
        try:
            age = self.app.cache.feed_age(self._current_tab)
        except Exception:
            age = None
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
        except Exception:
            return
        if age is None:
            panel.set_freshness("R to refresh")
            return
        panel.set_freshness(f"updated {_fmt_age_seconds(age)} · R to refresh")

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        if entry.get("_is_playlist"):
            self._open_playlist(entry.get("_playlist_name", ""))
            return
        if entry.get("_is_channel"):
            self._open_channel(entry)
            return
        self._open_video_action_menu(entry)

    def _open_video_action_menu(self, entry: dict) -> None:
        from src.tui.screens.video_action_modal import VideoActionModal

        # Hide queue action if video is already playing or queued
        current_id = self._audio_entry.get("id") if self._audio_entry else None
        entry_id = entry.get("id")
        queued_ids = {e.get("id") for e in self._audio_queue}
        hide_queue = (
            entry_id == current_id or entry_id in queued_ids or not self._audio_playing
        )

        def on_action(key: str | None) -> None:
            if not key:
                return
            dispatch = {
                "watch": self.action_watch,
                "watch_quality": self.action_watch_quality,
                "listen": lambda: self._start_audio(entry),
                "listen_quality": lambda: self._listen_quality(entry),
                "queue": self.action_queue_audio,
                "download": lambda: self.action_download(),
                "channel": lambda: self.action_channel(),
                "copy_url": lambda: self._copy_video_url(entry),
                "playlist": self.action_playlist,
                "browser": self.action_browser,
            }
            fn = dispatch.get(key)
            if fn:
                fn()

        self.app.push_screen(VideoActionModal(entry, hide_queue=hide_queue), on_action)

    # ── Audio player ──────────────────────────────────────────────────────────

    def _get_valid_stream_url(self, vid: str, kind: str = "audio") -> str | None:
        """Return a prefetched stream URL if available and not expired.

        kind: "audio" or "video"
        Returns None if unavailable or expired (5-min safety margin).
        """
        import time
        cached = self._stream_urls.get(vid)
        if not cached:
            return None
        url_key = f"{kind}_url"
        url = cached.get(url_key)
        if not url:
            return None
        expire = cached.get("expire", 0)
        if expire and (expire - time.time()) < 300:
            _logger.debug("prefetched %s URL for %s expired, falling back", kind, vid)
            return None
        fetched_at = cached.get("fetched_at", 0)
        if fetched_at and (time.time() - fetched_at) > 18000:
            _logger.debug("prefetched %s URL for %s too old, falling back", kind, vid)
            return None
        return url

    @property
    def _audio_playing(self) -> bool:
        return self._audio_proc is not None and self._audio_proc.poll() is None

    def _action_bar(self) -> ActionBar:
        return self.query_one("#detail-panel", DetailPanel).action_bar

    def _start_audio(self, entry: dict, *, ytdl_format: str = "") -> None:
        if self._audio_playing:
            self.notify(
                "Audio already playing — press s to stop first.", severity="warning"
            )
            return
        self._audio_entry = entry
        self._audio_stopped = False
        self._audio_session += 1
        session = self._audio_session
        self._sb_segments = []
        self._sb_skipped = set()
        self._log(f"[dim]Audio start: {entry.get('title', '')[:60]}[/dim]")
        self._action_bar().set_player_mode(entry, queue_len=len(self._audio_queue))
        self._refresh_queue_hint()
        self._launch_audio_worker(entry, session, ytdl_format=ytdl_format)
        self._audio_poll_timer = self.set_interval(0.5, self._poll_audio_ipc)

    def _stop_audio(self, *, keep_player_mode: bool = False) -> None:
        self._log("[dim]Audio stop[/dim]")
        self._audio_stopped = True
        self._sb_segments = []
        self._sb_skipped = set()
        if self._audio_proc and self._audio_proc.poll() is None:
            from src.player import send_ipc_command

            send_ipc_command({"command": ["quit"]}, socket_path=_get_audio_socket())
            from src.platform import terminate_process
            terminate_process(self._audio_proc, timeout=2.0)
        self._audio_proc = None
        self._audio_entry = None
        if self._audio_poll_timer:
            self._audio_poll_timer.stop()
            self._audio_poll_timer = None
        if not keep_player_mode:
            self._action_bar().set_actions_mode()
        from src.platform import cleanup_ipc
        cleanup_ipc(_get_audio_socket())

    @work(thread=True, exclusive=True, group="audio_player")
    def _launch_audio_worker(
        self, entry: dict, session: int, *, ytdl_format: str = ""
    ) -> None:
        from src import player as player_mod

        # Bail if a newer session already started (e.g. user skipped before we ran)
        if self._audio_stopped or session != self._audio_session:
            return

        vid = entry.get("id", "")
        if (
            vid
            and hasattr(self.app, "cache")
            and hasattr(self.app.cache, "suppress_video")
        ):
            self.app.cache.suppress_video(vid)

        # Fetch SponsorBlock segments (runs in worker thread — safe to block)
        if vid and self.app.config.sponsorblock_enabled:
            from src.sponsorblock import fetch_segments
            segments = fetch_segments(vid, self.app.config.sponsorblock_categories)
            self._sb_segments = segments
            self.app.call_from_thread(self._action_bar().set_segments, segments)

        url = entry.get("_local_path") or f"https://www.youtube.com/watch?v={vid}"
        title = entry.get("title", "")
        cookie_args = self.app.config.cookie_args()

        # Use prefetched audio URL if available and no custom quality selected
        use_prefetched = False
        if not entry.get("_local_path") and not ytdl_format and vid:
            prefetched_audio = self._get_valid_stream_url(vid, "audio")
            # If not ready yet, wait for the in-flight prefetch (max 2s)
            if not prefetched_audio:
                event = self._stream_url_ready.get(vid)
                if event:
                    event.wait(timeout=2.0)
                    prefetched_audio = self._get_valid_stream_url(vid, "audio")
            if prefetched_audio:
                url = prefetched_audio
                use_prefetched = True
                _logger.debug("audio: using prefetched URL for %s", vid)

        mpv_exe = player_mod._mpv_exe(headless=True)
        if not mpv_exe:
            from src.platform import install_hint, IS_WINDOWS
            hint = (
                "re-run setup.ps1 (it downloads a standalone headless mpv.exe). "
                "mpv.net opens a GUI window and cannot be used for background audio."
                if IS_WINDOWS else install_hint('mpv')
            )
            self.app.call_from_thread(
                self._log, f"[red]Error: no headless mpv found — {hint}[/red]"
            )
            self.app.call_from_thread(
                self.notify, f"No headless mpv found — {hint}", severity="error"
            )
            self.app.call_from_thread(self._stop_audio)
            return

        input_conf = player_mod._write_input_conf()
        cmd = [
            mpv_exe,
            f"--input-conf={input_conf}",
            f"--input-ipc-server={_get_audio_socket()}",
            "--no-video",
            "--force-window=no",
            "--no-terminal",
            "--msg-level=all=error",
            "--cache=yes",
            "--demuxer-max-bytes=150M",
            "--demuxer-readahead-secs=30",
        ]
        if title:
            cmd += [f"--title={title}"]
        if ytdl_format:
            cmd += [f"--ytdl-format={ytdl_format}"]
        if not use_prefetched:
            ytdl_raw = player_mod._cookie_args_to_ytdl_raw(cookie_args or [])
            if ytdl_raw:
                cmd += [f"--ytdl-raw-options={ytdl_raw}"]
        cmd += ["--", url]

        _logger.debug("audio mpv cmd: %s", " ".join(cmd))

        stderr_text = ""
        returncode: int | None = None
        try:
            from src.platform import get_popen_kwargs
            self._audio_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                **get_popen_kwargs(headless=True),
            )
            proc = self._audio_proc
            from src import history
            history.add(entry)
            # communicate() drains stderr while waiting — avoids the pipe
            # buffer filling up and deadlocking mpv if it spews errors.
            try:
                _out, stderr_text = proc.communicate()
            except Exception:
                stderr_text = ""
            returncode = proc.returncode
        except FileNotFoundError:
            from src.platform import install_hint
            hint = install_hint('mpv')
            self.app.call_from_thread(
                self._log, f"[red]Error: mpv not found — install with: {hint}[/red]"
            )
            self.app.call_from_thread(
                self.notify,
                f"mpv not found — install with: {hint}",
                severity="error",
            )
            self.app.call_from_thread(self._stop_audio)
            return
        except OSError as exc:
            self.app.call_from_thread(
                self._log, f"[red]Error: failed to launch mpv: {exc}[/red]"
            )
            self.app.call_from_thread(
                self.notify, f"Failed to launch mpv: {exc}", severity="error"
            )
            self.app.call_from_thread(self._stop_audio)
            return
        finally:
            try:
                os.unlink(input_conf)
            except OSError:
                pass

        stderr_text = (stderr_text or "").strip()
        # Bail if a newer session has taken over while we were playing.
        if self._audio_stopped or session != self._audio_session:
            if stderr_text:
                _logger.debug("audio mpv stderr (stale session): %s", stderr_text)
            return

        # mpv exit codes:
        #   0 = clean EOF, 4 = quit by user (both successful from our POV)
        #   1 = error initializing, 2 = error during playback,
        #   3 = killed by signal (e.g. terminate from _stop_audio)
        if returncode in (0, 4):
            if stderr_text:
                _logger.debug("audio mpv stderr (rc=%s): %s", returncode, stderr_text)
            self.app.call_from_thread(self._on_audio_finished, entry)
        elif returncode == 3:
            # We killed it via _stop_audio; nothing to report.
            if stderr_text:
                _logger.debug("audio mpv terminated (rc=3): %s", stderr_text)
        else:
            # Real failure — log everything and surface a notification.
            _logger.warning(
                "audio mpv failed (rc=%s) for %s: %s",
                returncode,
                vid,
                stderr_text or "(no stderr output)",
            )
            self.app.call_from_thread(self._on_audio_failed, entry, returncode, stderr_text)

    def _on_audio_finished(self, entry: dict) -> None:
        self._log(f"[dim]Audio finished: {entry.get('title', '')[:60]}[/dim]")
        title = entry.get("title", "")
        self._audio_proc = None
        self._audio_entry = None
        if self._audio_poll_timer:
            self._audio_poll_timer.stop()
            self._audio_poll_timer = None
        if self._audio_queue:
            next_entry = self._audio_queue.pop(0)
            if title:
                self.notify(f"✓ {title[:40]}", timeout=3)
            self._start_audio(next_entry)  # _start_audio calls _refresh_queue_hint
        else:
            self._action_bar().set_actions_mode()
            if title:
                self.notify(f"✓ Finished: {title[:50]}", timeout=4)

    def _on_audio_failed(
        self, entry: dict, returncode: int | None, stderr_text: str
    ) -> None:
        """mpv exited with a non-zero/non-quit code — playback never succeeded.

        We do NOT add to history (nothing was played) and we surface the actual
        error to the user so they don't see a misleading "Finished" toast.
        """
        title = entry.get("title", "") or entry.get("id", "")
        self._audio_proc = None
        self._audio_entry = None
        if self._audio_poll_timer:
            self._audio_poll_timer.stop()
            self._audio_poll_timer = None

        # Pull the most useful one-line summary out of mpv's stderr.
        first_err = ""
        for line in (stderr_text or "").splitlines():
            line = line.strip()
            if line:
                first_err = line
                break
        detail = first_err or f"exit code {returncode}"

        self._log(f"[red]Audio failed: {title[:50]} — {detail}[/red]")
        self.notify(
            f"✗ Audio failed: {title[:40]} ({detail[:80]})",
            severity="error",
            timeout=8,
        )

        # Skip ahead to whatever the user queued next, if anything.
        if self._audio_queue:
            next_entry = self._audio_queue.pop(0)
            self._start_audio(next_entry)
        else:
            self._action_bar().set_actions_mode()

    def _poll_audio_ipc(self) -> None:
        if not self._audio_playing:
            return
        from src.player import poll_audio_properties

        pos, dur, paused = poll_audio_properties(socket_path=_get_audio_socket())
        if pos is not None and dur is not None:
            self._action_bar().update_progress(pos, dur, paused)

            # Auto-skip sponsor segments
            if self.app.config.sponsorblock_auto_skip and self._sb_segments:
                for i, seg in enumerate(self._sb_segments):
                    if i in self._sb_skipped:
                        continue
                    if seg.start <= pos < seg.end:
                        self._sb_skipped.add(i)
                        skip_dur = int(seg.end - seg.start)
                        from src.player import send_ipc_command
                        send_ipc_command(
                            {"command": ["seek", seg.end, "absolute"]},
                            socket_path=_get_audio_socket(),
                        )
                        self.notify(
                            f"Skipped: {seg.category} ({skip_dur}s)", timeout=3
                        )
                        break

    def _listen_quality(self, entry: dict) -> None:
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                self._start_audio(entry, ytdl_format=fmt)

        self.app.push_screen(QualityModal(audio_only=True), on_fmt)

    # ── Context-aware audio bindings ──────────────────────────────────────────

    def action_listen_or_seek(self) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["seek", 5, "relative"]})
        else:
            entry = self._selected_entry()
            if entry and not entry.get("_is_playlist"):
                self._start_audio(entry)

    def action_listen_q_or_seek_big(self) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["seek", 10, "relative"]})
        else:
            entry = self._selected_entry()
            if entry and not entry.get("_is_playlist"):
                self._listen_quality(entry)

    def action_audio_seek_back(self) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["seek", -5, "relative"]})

    def action_audio_seek_back_big(self) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["seek", -10, "relative"]})

    def action_audio_pause(self) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["cycle", "pause"]})

    def action_audio_stop_or_subscribe(self) -> None:
        if self._audio_playing:
            self._audio_queue.clear()
            self._stop_audio()
        else:
            self.action_subscribe_entry()

    def _audio_pct(self, pct: int) -> None:
        if self._audio_playing:
            self._audio_ipc({"command": ["seek", pct, "absolute-percent"]})

    def action_audio_pct_0(self) -> None:
        self._audio_pct(0)

    def action_audio_pct_10(self) -> None:
        self._audio_pct(10)

    def action_audio_pct_20(self) -> None:
        self._audio_pct(20)

    def action_audio_pct_30(self) -> None:
        self._audio_pct(30)

    def action_audio_pct_40(self) -> None:
        self._audio_pct(40)

    def action_audio_pct_50(self) -> None:
        self._audio_pct(50)

    def action_audio_pct_60(self) -> None:
        self._audio_pct(60)

    def action_audio_pct_70(self) -> None:
        self._audio_pct(70)

    def action_audio_pct_80(self) -> None:
        self._audio_pct(80)

    def action_audio_pct_90(self) -> None:
        self._audio_pct(90)

    def _audio_ipc(self, cmd: dict) -> None:
        from src.player import send_ipc_command

        send_ipc_command(cmd, socket_path=_get_audio_socket())

    # ── Video playback (Delegates to WatchModal) ──────────────────────────────

    def action_watch(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return

        _logger.info("user action: watch %s (%s)", entry.get("id", "?"), (entry.get("title") or "")[:60])
        from src.tui.screens.watch_modal import WatchModal

        vid = entry.get("id", "")
        stream_urls = self._stream_urls.get(vid) if vid else None
        stream_ready = self._stream_url_ready.get(vid) if vid else None
        self.app.push_screen(WatchModal(
            entry,
            stream_urls=stream_urls,
            stream_ready=stream_ready,
            stream_urls_map=self._stream_urls,
        ))

    def action_watch_quality(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                from src.tui.screens.watch_modal import WatchModal

                self.app.push_screen(WatchModal(entry, ytdl_format=fmt))

        self.app.push_screen(QualityModal(audio_only=False), on_fmt)

    # ── Download ──────────────────────────────────────────────────────────────

    def action_download(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist") or entry.get("_is_channel"):
            return
        title = entry.get("title", entry.get("id", ""))
        from src.tui.screens.download_picker_modal import DownloadPickerModal

        def on_pick(result) -> None:
            if result is None:
                return
            dl_type, fmt = result
            audio_only = (dl_type == "audio")
            self._open_download(entry, audio_only=audio_only, fmt=fmt)

        self.app.push_screen(DownloadPickerModal(title=title), on_pick)

    def _open_download(self, entry: dict, *, audio_only: bool, fmt: str = "") -> None:
        from src.tui.screens.download_modal import DownloadModal

        vid = entry.get("id", "")
        mode = "audio" if audio_only else "video"
        title = entry.get("title", vid)

        def on_done(success: bool | None) -> None:
            if success:
                self.notify(chr(10003) + " Downloaded " + mode + ": " + title[:40], timeout=5)
            else:
                self.notify(
                    chr(10007) + " Download failed or cancelled", severity="warning", timeout=4
                )

        self.app.push_screen(DownloadModal(vid, entry, audio_only=audio_only, fmt=fmt), on_done)

    def action_channel(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        self._open_channel(entry)

    def _open_channel(self, entry: dict) -> None:
        from src.tui.screens.channel_screen import ChannelScreen
        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            uid = entry.get("uploader_id") or entry.get("channel_id")
            if uid:
                url = "https://www.youtube.com/" + uid if uid.startswith("@") else "https://www.youtube.com/channel/" + uid
        if not url:
            self.notify("No channel URL found.", severity="warning")
            return
        name = entry.get("uploader") or entry.get("channel") or "Channel"
        self.app.push_screen(ChannelScreen(channel_url=url, channel_name=name))

    # ── Subscribe / Playlist / Browser ────────────────────────────────────────

    def action_subscribe_entry(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            uid = entry.get("uploader_id") or entry.get("channel_id")
            if uid:
                url = f"https://www.youtube.com/@{uid}"
        if url:
            import webbrowser

            webbrowser.open(url)
            channel = entry.get("uploader") or entry.get("channel") or "channel"
            self.notify(f"Opened {channel} in browser")
        else:
            self.notify("No channel URL available", severity="warning")

    def action_playlist(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.playlist_modal import PlaylistModal

        def on_done(_: None) -> None:
            detail = self.query_one("#detail-panel", DetailPanel)
            detail._update_playlists(entry.get("id", ""))

        self.app.push_screen(PlaylistModal(entry), on_done)

    def action_copy_url(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        self._copy_video_url(entry)

    def _copy_video_url(self, entry: dict) -> None:
        vid = entry.get("id", "")
        if not vid or vid.startswith("__"):
            self.notify("No URL available", severity="warning")
            return
        url = f"https://www.youtube.com/watch?v={vid}"
        from src.platform import clipboard_copy
        if clipboard_copy(url):
            self.notify("URL copied to clipboard")
        else:
            self.notify(f"URL: {url}", timeout=10)

    def action_queue_audio(self) -> None:
        if not self._audio_playing:
            return
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        entry_id = entry.get("id")
        current_id = self._audio_entry.get("id") if self._audio_entry else None
        if entry_id and entry_id == current_id:
            self.notify("Already playing this track", timeout=2)
            return
        if entry_id and any(e.get("id") == entry_id for e in self._audio_queue):
            self.notify("Already in queue", timeout=2)
            return
        self._audio_queue.append(entry)
        title = entry.get("title", "video")[:40]
        self.notify(f"Added to queue: {title}", timeout=3)
        self._refresh_queue_hint()

    def action_audio_skip(self) -> None:
        if not self._audio_playing or not self._audio_queue:
            return
        next_entry = self._audio_queue.pop(0)
        self._stop_audio(keep_player_mode=True)
        self._start_audio(next_entry)  # _start_audio calls _refresh_queue_hint

    def action_browser(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        if vid and not vid.startswith("__"):
            import webbrowser

            webbrowser.open(f"https://www.youtube.com/watch?v={vid}")
            self.notify("Opened in browser")

    # ── Search ────────────────────────────────────────────────────────────────

    def action_search(self) -> None:
        self._open_search_dialog()

    def _open_search_dialog(self) -> None:
        from src.tui.screens.search_modal import SearchModal

        def on_result(query: str | None) -> None:
            if not query:
                _logger.debug("search dialog cancelled")
                # Do NOT touch tabs.active here — setting it programmatically
                # fires on_tabs_tab_activated again for the current tab, which
                # triggers a full _load_view reload and wipes the list.
                # The tab bar is already showing the correct active tab visually;
                # no action is needed on cancel.
                return
            tabs = self.query_one("#nav-tabs", Tabs)
            _logger.info("search query: %r", query)
            self._search_query = query
            self._current_tab = "search"
            self._nav_stack.clear()
            for tab in tabs.query(Tab):
                if tab.id == "search":
                    tab.label = f"🔍 {query[:20]}"
                    break
            self._activating_search_programmatically = True
            tabs.active = "search"
            self._load_view("search")

        self.app.push_screen(SearchModal(), on_result)

    # ── Playlist nav ──────────────────────────────────────────────────────────

    def _open_playlist(self, name: str) -> None:
        self._nav_stack.append(self._current_tab)
        self._current_tab = f"playlist:{name}"
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        panel.set_breadcrumb(f"🎵 {name}  ← backspace to go back")
        self.query_one("#detail-panel", DetailPanel).clear()
        self._stream_view(f"playlist:{name}")

    def action_nav_back(self) -> None:
        if not self._nav_stack:
            return
        prev = self._nav_stack.pop()
        self._current_tab = prev
        tabs = self.query_one("#nav-tabs", Tabs)
        if prev in ("home", "subscriptions", "history", "library", "playlists", "help"):
            tabs.active = prev
        elif prev == "search":
            self._load_view("search")

    # ── List navigation ───────────────────────────────────────────────────────

    def _selected_entry(self) -> dict | None:
        return self.query_one("#video-list-panel", VideoListPanel).selected_entry

    def action_cursor_down(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_up()

    # ── Page navigation ───────────────────────────────────────────────────────

    def action_page_next(self) -> None:
        """Switch to next page. Auto-fetches more if on the last page of a feed."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        if panel.is_loading:
            return
        if panel.can_go_next():
            panel.load_page(panel.current_page + 1)
            # Proactive: if we just landed on the last page, start fetching more
            if not panel.can_go_next() and self._current_tab in _PAGED_TABS:
                self._prefetch_more_pages()
        elif self._current_tab in _PAGED_TABS:
            self._fetch_more_pages()

    def action_page_prev(self) -> None:
        """Switch to previous page. No-op if already on page 1."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        if panel.can_go_prev():
            panel.load_page(panel.current_page - 1)

    def action_page_first(self) -> None:
        """Jump to the first page."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        if panel.current_page != 1 and 1 in panel._pages:
            panel.load_page(1)

    def action_page_last(self) -> None:
        """Jump to the last fetched page."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        last = panel.total_pages
        if panel.current_page != last and last in panel._pages:
            panel.load_page(last)

    def on_video_list_panel_page_change_requested(
        self, message: VideoListPanel.PageChangeRequested
    ) -> None:
        """Handle page change from PageIndicator button clicks."""
        if message.direction > 0:
            self.action_page_next()
        else:
            self.action_page_prev()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        _logger.info("user refresh (tab=%s)", self._current_tab)
        if self._current_tab in _FEED_TABS:
            self.app.cache.clear_feed(self._current_tab)
            if self._current_tab == "home":
                self.app.cache.clear_home_stash()
        self._load_view(self._current_tab)
        self.notify(f"Refreshing {self._current_tab}…", timeout=2)

    # ── Help / Settings ───────────────────────────────────────────────────────

    def action_toggle_help(self) -> None:
        from src.tui.screens.help_screen import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_settings(self) -> None:
        from src.tui.screens.settings_modal import SettingsModal

        self.app.push_screen(SettingsModal())

    # ── Debug log ─────────────────────────────────────────────────────────────

    def action_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        log = self.query_one("#debug-log", RichLog)
        log.display = self._log_visible
        if self._log_visible:
            if not _logger.is_debug():
                # Show a one-time hint explaining how to enable real logging.
                log.clear()
                log.write("[yellow]Debug logging is disabled.[/yellow]")
                log.write("[dim]Restart TermTube with the [bold]--debug[/bold] flag to enable logging:[/dim]")
                log.write("[dim]    termtube --debug[/dim]")
                log.write("[dim]Logs are written to $TMPDIR/TermTube/<timestamp>.log and mirrored here.[/dim]")
            self.notify("Debug log visible — Ctrl+D to hide", timeout=2)

    # ── Logger sink ───────────────────────────────────────────────────────────

    _LOG_LEVEL_STYLES = {
        "DEBUG": "dim",
        "INFO": "cyan",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red bold",
    }

    def _on_log_record(self, level: str, msg: str) -> None:
        """Logger callback. Invoked from arbitrary threads — must be safe."""
        try:
            self.app.call_from_thread(self._write_log_to_widget, level, msg)
        except Exception:
            # App may be shutting down; nothing we can do.
            pass

    def _write_log_to_widget(self, level: str, msg: str) -> None:
        color = self._LOG_LEVEL_STYLES.get(level, "white")
        try:
            safe_msg = msg.replace("[", "\\[") if msg else ""
            self.query_one("#debug-log", RichLog).write(
                f"[{color}]\\[{level[0]}][/{color}] {safe_msg}"
            )
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        """Write a Rich-markup status message to the debug log + log file.

        No-op when --debug is off so we don't pay rendering cost.
        """
        if not _logger.is_debug():
            return
        try:
            self.query_one("#debug-log", RichLog).write(msg)
        except Exception:
            pass
        # Mirror plain text to the file/stderr handlers but skip the TUI sink
        # (we've already drawn the markup version above).
        plain = re.sub(r"\[/?[^\]]*\]", "", msg)
        _logger.file_only(plain)

    # ── Tab shortcuts ─────────────────────────────────────────────────────────

    def action_tab_home(self) -> None:
        self.query_one("#nav-tabs", Tabs).active = "home"

    def action_tab_subs(self) -> None:
        self.query_one("#nav-tabs", Tabs).active = "subscriptions"

    def action_tab_search(self) -> None:
        self._open_search_dialog()

    def action_tab_history(self) -> None:
        self.query_one("#nav-tabs", Tabs).active = "history"

    def action_tab_library(self) -> None:
        self.query_one("#nav-tabs", Tabs).active = "library"

    def action_tab_playlists(self) -> None:
        self.query_one("#nav-tabs", Tabs).active = "playlists"

    def action_tab_help(self) -> None:
        self.action_toggle_help()

    # ── Nav picker ────────────────────────────────────────────────────────────

    def action_nav_picker(self) -> None:
        from src.tui.screens.nav_modal import NavModal

        def on_pick(tab_id: str | None) -> None:
            if not tab_id:
                return
            if tab_id == "search":
                self._open_search_dialog()
            elif tab_id == "help":
                self.action_toggle_help()
            else:
                self.query_one("#nav-tabs", Tabs).active = tab_id

        self.app.push_screen(NavModal(), on_pick)

    # ── Quit ──────────────────────────────────────────────────────────────────

    def action_quit_app(self) -> None:
        import threading

        _logger.info("user action: quit")
        # Save the quick-start stash so the next boot is instant.
        if self._current_tab in _FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self._stop_audio()
        try:
            import src.ytdlp as ytdlp

            ytdlp.kill_all_active()
        except Exception:
            pass
        threading.Timer(0.6, os._exit, args=(0,)).start()
        self.app.exit()
