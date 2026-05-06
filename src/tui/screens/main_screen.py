"""MainScreen — primary TUI screen with nav tabs, video list, and detail panel."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Literal

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, RichLog, Static, Tab, Tabs

from src import logger as _logger
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

# How many entries to fetch per home/subscriptions background load.
_HOME_FETCH_COUNT = 100

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


def _fmt_age_seconds(secs: float) -> str:
    """Compact human age string for the freshness header (e.g. '4m ago', '2h ago')."""
    secs = int(secs)
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    return f"{days}d ago"


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

_AUDIO_SOCKET = "/tmp/termtube-mpv-audio.sock"

# ── Dwell / freshness tuning ──────────────────────────────────────────────────
# Cursor settles for this long before we kick the focus (yt-dlp) worker.
_FOCUS_DWELL_S = 0.20
# Cursor settles for this long before we kick the thumbnail render worker.
_THUMB_DWELL_S = 0.15
# Header freshness label refresh cadence (seconds).
_FRESHNESS_REFRESH_S = 60.0
# Tabs that show a streamed video feed.
_FEED_TABS = ("home", "subscriptions")
# Chafa RAM cache cap (entries).
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
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
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
        Binding("d", "dl_video", "DL Video", show=False),
        Binding("a", "dl_audio", "DL Audio", show=False),
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
        self._current_tab = "home"
        self._search_query: str = ""
        self._nav_stack: list[str] = []
        self._log_visible = False
        # Guard: True while we are programmatically activating the search tab
        # from a confirmed search result (so on_tabs_tab_activated skips the
        # modal re-open that would otherwise fire).
        self._activating_search_programmatically: bool = False
        # ── Audio player state ────────────────────────────────────────────────
        self._audio_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._audio_entry: dict | None = None
        self._audio_stopped = False
        self._audio_poll_timer = None
        self._audio_queue: list[dict] = []
        self._audio_session: int = 0  # incremented per start; old workers bail if stale
        # ── Focus / thumbnail dwell-driven workers ────────────────────────────
        self._focus_dwell_timer: Timer | None = None
        self._thumb_dwell_timer: Timer | None = None
        self._focus_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._thumb_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._focus_session: int = 0
        self._thumb_session: int = 0
        # Cursor direction tracking for one-neighbour prefetch.
        self._last_focus_id: str = ""
        self._last_cursor_dir: Literal["up", "down"] | None = None
        # In-RAM LRU of rendered chafa output keyed by (vid, cols, rows, fmt).
        self._chafa_ram_cache: OrderedDict[tuple[str, int, int, str], str] = OrderedDict()
        # ── Feed loading state ────────────────────────────────────────────────
        # True while the home/subs background fetch worker is running.
        # Used to suppress spurious TabActivated events that Textual fires
        # during rapid ListView DOM mutations (DOM mutation can shift focus to
        # the Tabs widget, which fires on_tabs_tab_activated, which would wipe
        # the list). Guard: if the tab is already current and we are loading,
        # the activation is spurious — discard it.
        self._home_loading: bool = False
        # Freshness label refresh timer.
        self._freshness_timer: Timer | None = None

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
        if _logger.is_debug():
            _logger.register_tui_sink(self._on_log_record)
            _logger.info("MainScreen mounted; debug log wired to TUI sink")
            self._log(f"[green]Debug logging active[/green] — file: [dim]{_logger.log_file()}[/dim]")
        # Periodic freshness label refresh ("updated 4m ago").
        self._freshness_timer = self.set_interval(_FRESHNESS_REFRESH_S, self._update_freshness_label)
        self.set_timer(0.4, self._maybe_show_image_warning)

    def _maybe_show_image_warning(self) -> None:
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE
        if _HAS_TEXTUAL_IMAGE:
            return
        if self.app.config.get("thumbnail_warning_dismissed", False):
            return
        from src.tui.screens.image_warning_modal import ImageWarningModal

        def _on_done(never_show: bool) -> None:
            if never_show:
                self.app.config._data["thumbnail_warning_dismissed"] = True
                self.app.config.save()

        self.app.push_screen(ImageWarningModal(), _on_done)

    # ── Tab switching ─────────────────────────────────────────────────────────

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if not event.tab or not event.tab.id:
            return
        tab_id = event.tab.id
        # Guard: Textual fires spurious TabActivated events when ListView DOM
        # mutations (appending new items) shift focus to the Tabs widget.
        # If the activated tab is already the current one AND a feed worker
        # is running, this is a false positive — discard it silently instead
        # of wiping and reloading the list.
        if tab_id == self._current_tab and self._home_loading:
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
        """Persist up to 12 unconsumed buffer entries to the quick-start stash.

        Only applies to the home feed. Saves entries the user hasn't yet
        scrolled past — those are the most likely to still be relevant on
        the next boot.
        """
        if feed_key != "home":
            return
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
            buf = panel._buffer
            cursor = panel.cursor_index()
            # Start saving from one past the current cursor position.
            start = (cursor + 1) if cursor is not None else panel.visible_count
            tail = buf[start:]
            if tail:
                self.app.cache.put_home_stash(tail)
                _logger.debug("stash: saved %d entries (start=%d)", len(tail[:12]), start)
        except Exception as exc:
            _logger.debug("stash save error: %s", exc)

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        self.query_one("#detail-panel", DetailPanel).clear()
        # Track whether a feed loader is running so the TabActivated guard works.
        self._home_loading = (view in _FEED_TABS)
        self._stream_view(view)

    # ── Streaming workers ─────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str) -> None:
        """Background worker: dispatch streaming for any tab view."""
        panel = self.query_one("#video-list-panel", VideoListPanel)
        config = self.app.config
        cache = self.app.cache

        sync_handled = False
        try:
            if view in _FEED_TABS:
                import src.ytdlp as ytdlp
                self._stream_feed(view, panel, config, cache, ytdlp)
                sync_handled = True  # _stream_feed owns finish_loading
            elif view == "search":
                if not self._search_query:
                    self.app.call_from_thread(
                        panel.set_empty_message, "Press / to search"
                    )
                    self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)
                    return
                import src.ytdlp as ytdlp
                for entry in ytdlp.stream_search(self._search_query, config, cache):
                    self.app.call_from_thread(panel.append_entry, entry)
            elif view == "history":
                from src import history as hist
                for entry in hist.iter_entries():
                    self.app.call_from_thread(panel.append_entry, entry)
            elif view == "library":
                from src import library as lib
                for entry in lib.all_entries(config.video_dir, config.audio_dir):
                    self.app.call_from_thread(panel.append_entry, entry)
            elif view == "playlists":
                self._load_playlists_sync(panel)
                sync_handled = True
            elif view.startswith("playlist:"):
                self._load_playlist_videos_sync(view[len("playlist:"):], panel, cache)
                sync_handled = True
        except Exception as exc:
            msg = str(exc)
            self.app.call_from_thread(panel.set_error_message, f"⚠ {msg}")
            self.app.call_from_thread(self._log, f"[red]Error in {view}: {msg}[/red]")
            self.app.call_from_thread(self.query_one(AppHeader).set_status_error)
            self._home_loading = False
            return

        if not sync_handled:
            self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)
            self.app.call_from_thread(panel.finish_loading)
        if view in _FEED_TABS:
            self.app.call_from_thread(self._update_freshness_label)

    def _stream_feed(self, feed_key: str, panel, config, cache, ytdlp) -> None:
        """Home / subscriptions feed loader.

        Boot sequence:
          1. If a quick-start stash exists (from the previous session), load
             those entries immediately — they appear before the spinner so
             the user has something to look at right away.
          2. Fetch up to _HOME_FETCH_COUNT fresh entries from yt-dlp,
             appending each one as it arrives (no DOM wipe, no full reload).
          3. Finish: hide spinner, update header count.
        """
        is_suppressed = cache.is_suppressed

        # Step 1 — quick-start stash (home only).
        if feed_key == "home":
            stash = cache.get_home_stash()
            if stash:
                _logger.debug("feed %s: loading %d stash entries", feed_key, len(stash))
                for entry in stash:
                    vid = entry.get("id", "")
                    if vid and is_suppressed(vid):
                        continue
                    self.app.call_from_thread(panel.append_entry, entry)

        # Step 2 — fresh yt-dlp fetch (spinner on).
        self.app.call_from_thread(self.query_one(AppHeader).set_status_loading)
        self.app.call_from_thread(panel.set_fetching_more, True)

        try:
            count = 0
            for entry in ytdlp.stream_flat(
                ytdlp.FEED_URLS[feed_key],
                config,
                cache,
                feed_key=feed_key,
                max_count=_HOME_FETCH_COUNT,
            ):
                vid = entry.get("id")
                if feed_key == "home" and vid and is_suppressed(vid):
                    continue
                self.app.call_from_thread(panel.append_entry, entry)
                count += 1
            _logger.debug("feed %s: fetched %d entries", feed_key, count)
        finally:
            self._home_loading = False
            self.app.call_from_thread(panel.set_fetching_more, False)
            self.app.call_from_thread(panel.finish_loading)
            self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)

    def _load_playlists_sync(self, panel) -> None:
        from src import playlist

        names = playlist.list_names()
        if not names:
            self.app.call_from_thread(
                panel.set_empty_message, "No playlists. Select a video and press p."
            )
            return
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
            self.app.call_from_thread(panel.append_entry, entry)
        self.app.call_from_thread(panel.finish_loading)

    def _load_playlist_videos_sync(self, name: str, panel, cache) -> None:
        from src import playlist

        ids = playlist.get_playlist(name)
        if not ids:
            self.app.call_from_thread(
                panel.set_empty_message, f'Playlist "{name}" is empty.'
            )
            return
        for vid_id in ids:
            entry = cache.get_video_raw(vid_id) or {
                "id": vid_id,
                "title": vid_id,
                "uploader": "",
            }
            self.app.call_from_thread(panel.append_entry, entry)
        self.app.call_from_thread(panel.finish_loading)

    # ── Detail panel events ───────────────────────────────────────────────────

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        entry = message.entry
        vid = entry.get("id", "")
        detail = self.query_one("#detail-panel", DetailPanel)
        detail.update_basic(entry)
        self._update_cursor_direction(vid)
        self._cancel_pending_focus_and_thumb()
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
        # Best-effort kill of any subprocess still running. Safe even after exit.
        for attr in ("_focus_proc", "_thumb_proc"):
            proc = getattr(self, attr, None)
            if proc is None:
                continue
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            setattr(self, attr, None)

    def _update_cursor_direction(self, vid: str) -> None:
        """Update _last_cursor_dir based on buffer index movement."""
        if not vid or not self._last_focus_id or vid == self._last_focus_id:
            self._last_focus_id = vid
            return
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
            old_idx = panel._buffer_index.get(self._last_focus_id)
            new_idx = panel._buffer_index.get(vid)
            if old_idx is not None and new_idx is not None:
                self._last_cursor_dir = "down" if new_idx > old_idx else "up"
        except Exception:
            pass
        self._last_focus_id = vid

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

    @work(thread=True, exclusive=True, group="focus")
    def _focus_worker(self, vid: str, entry: dict, session: int) -> None:
        """Fetch full metadata for vid and apply to UI. Latest-wins via session."""
        import src.ytdlp as ytdlp

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

        if full is None or session != self._focus_session:
            return
        # Apply to UI via call_from_thread; refresh_metadata also guards on
        # current_id internally so a late callback can't paint the wrong video.
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
            self.app.call_from_thread(panel.update_entry_by_id, vid, full)
            self.app.call_from_thread(
                self.query_one("#detail-panel", DetailPanel).refresh_metadata, full
            )
        except Exception:
            pass

        # Cheap one-neighbour prefetch — populates cache so the next cursor
        # step is instant. Bounded: at most one extra fetch per focus dispatch.
        # Bails immediately if the user has moved on.
        if session != self._focus_session or self._last_cursor_dir is None:
            return
        try:
            panel = self.query_one("#video-list-panel", VideoListPanel)
        except Exception:
            return
        offset = 1 if self._last_cursor_dir == "down" else -1
        neighbor = panel.neighbor_id(vid, offset)
        if not neighbor or neighbor.startswith("__"):
            return
        cached = self.app.cache.get_video(neighbor)
        if cached and cached.get("description") is not None:
            return  # already enriched
        try:
            ytdlp.fetch_full(
                neighbor, self.app.config, self.app.cache, on_proc_started=_on_proc
            )
        except Exception as exc:
            _logger.debug("neighbour prefetch error for %s: %s", neighbor, exc)
        finally:
            self._focus_proc = None

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
                "dl_video": self.action_dl_video,
                "dl_audio": self.action_dl_audio,
                "copy_url": lambda: self._copy_video_url(entry),
                "subscribe": self.action_subscribe_entry,
                "playlist": self.action_playlist,
                "browser": self.action_browser,
            }
            fn = dispatch.get(key)
            if fn:
                fn()

        self.app.push_screen(VideoActionModal(entry, hide_queue=hide_queue), on_action)

    # ── Audio player ──────────────────────────────────────────────────────────

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
        self._log(f"[dim]Audio start: {entry.get('title', '')[:60]}[/dim]")
        self._action_bar().set_player_mode(entry, queue_len=len(self._audio_queue))
        self._refresh_queue_hint()
        self._launch_audio_worker(entry, session, ytdl_format=ytdl_format)
        self._audio_poll_timer = self.set_interval(0.5, self._poll_audio_ipc)

    def _stop_audio(self, *, keep_player_mode: bool = False) -> None:
        self._log("[dim]Audio stop[/dim]")
        self._audio_stopped = True
        if self._audio_proc and self._audio_proc.poll() is None:
            from src.player import send_ipc_command

            send_ipc_command({"command": ["quit"]}, socket_path=_AUDIO_SOCKET)
            try:
                self._audio_proc.terminate()
            except Exception:
                pass
        self._audio_proc = None
        self._audio_entry = None
        if self._audio_poll_timer:
            self._audio_poll_timer.stop()
            self._audio_poll_timer = None
        if not keep_player_mode:
            self._action_bar().set_actions_mode()
        try:
            os.unlink(_AUDIO_SOCKET)
        except OSError:
            pass

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

        url = entry.get("_local_path") or f"https://www.youtube.com/watch?v={vid}"
        title = entry.get("title", "")
        cookie_args = self.app.config.cookie_args

        input_conf = player_mod._write_input_conf()
        # Allow mpv to surface errors on stderr (we capture them via PIPE).
        # We still suppress chatty status-line output by routing all categories
        # to "error" — only error/fatal messages reach us.
        cmd = [
            "mpv",
            f"--input-conf={input_conf}",
            f"--input-ipc-server={_AUDIO_SOCKET}",
            "--no-video",
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
        ytdl_raw = player_mod._cookie_args_to_ytdl_raw(cookie_args or [])
        if ytdl_raw:
            cmd += [f"--ytdl-raw-options={ytdl_raw}"]
        cmd += ["--", url]

        _logger.debug("audio mpv cmd: %s", " ".join(cmd))

        stderr_text = ""
        returncode: int | None = None
        try:
            self._audio_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            # communicate() drains stderr while waiting — avoids the pipe
            # buffer filling up and deadlocking mpv if it spews errors.
            try:
                _out, stderr_text = self._audio_proc.communicate()
            except Exception:
                stderr_text = ""
            returncode = self._audio_proc.returncode
        except FileNotFoundError:
            self.app.call_from_thread(
                self._log, "[red]Error: mpv not found — install with: brew install mpv[/red]"
            )
            self.app.call_from_thread(
                self.notify,
                "mpv not found — install with: brew install mpv",
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
            from src import history

            history.add(entry)
            if stderr_text:
                # mpv sometimes prints non-fatal warnings even on a clean exit
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

        pos, dur, paused = poll_audio_properties(socket_path=_AUDIO_SOCKET)
        if pos is not None and dur is not None:
            self._action_bar().update_progress(pos, dur, paused)

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

        send_ipc_command(cmd, socket_path=_AUDIO_SOCKET)

    # ── Video playback (Delegates to WatchModal) ──────────────────────────────

    def action_watch(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return

        _logger.info("user action: watch %s (%s)", entry.get("id", "?"), (entry.get("title") or "")[:60])
        # Open our new modal seamlessly
        from src.tui.screens.watch_modal import WatchModal

        self.app.push_screen(WatchModal(entry))

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

    def action_dl_video(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        _logger.info("user action: download video %s", entry.get("id", "?"))
        self._open_download(entry, audio_only=False)

    def action_dl_audio(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        _logger.info("user action: download audio %s", entry.get("id", "?"))
        self._open_download(entry, audio_only=True)

    def _open_download(self, entry: dict, *, audio_only: bool) -> None:
        from src.tui.screens.download_modal import DownloadModal

        vid = entry.get("id", "")
        mode = "audio" if audio_only else "video"
        title = entry.get("title", vid)

        def on_done(success: bool | None) -> None:
            if success:
                self.notify(f"✓ Downloaded {mode}: {title[:40]}", timeout=5)
            else:
                self.notify(
                    "✗ Download failed or cancelled", severity="warning", timeout=4
                )

        self.app.push_screen(DownloadModal(vid, entry, audio_only=audio_only), on_done)

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
        for cmd in (
            ["pbcopy"],
            ["xclip", "-selection", "clipboard"],
            ["wl-copy"],
        ):
            try:
                subprocess.run(cmd, input=url.encode(), check=True, capture_output=True)
                self.notify("URL copied to clipboard")
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
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

    def action_cursor_top(self) -> None:
        _logger.debug("scroll: top")
        self.query_one("#video-list-panel", VideoListPanel).cursor_to_top()

    def action_cursor_bottom(self) -> None:
        _logger.debug("scroll: bottom")
        self.query_one("#video-list-panel", VideoListPanel).cursor_to_bottom()

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
            # Escape the level glyph so Rich treats it literally; the message
            # itself may legitimately contain bracketed text — pass it raw.
            self.query_one("#debug-log", RichLog).write(
                f"[{color}]\\[{level[0]}][/{color}] {msg}"
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
