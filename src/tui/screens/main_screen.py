"""MainScreen — primary TUI screen with nav tabs, video list, and detail panel."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from datetime import datetime

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, RichLog, Static, Tab, Tabs

from src import logger as _logger
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

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

_MIN_FEED_COUNT = 15
_AUDIO_SOCKET = "/tmp/termtube-mpv-audio.sock"


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
        # ── Audio player state ────────────────────────────────────────────────
        self._audio_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._audio_entry: dict | None = None
        self._audio_stopped = False
        self._audio_poll_timer = None
        self._audio_queue: list[dict] = []
        self._audio_session: int = 0  # incremented per start; old workers bail if stale

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
        # Wire the global logger so messages from any module appear in the
        # in-app debug window (Ctrl+D). Only fires when --debug is on.
        if _logger.is_debug():
            _logger.register_tui_sink(self._on_log_record)
            _logger.info("MainScreen mounted; debug log wired to TUI sink")
            self._log(f"[green]Debug logging active[/green] — file: [dim]{_logger.log_file()}[/dim]")
        self.set_interval(600.0, self._scheduled_home_refresh)
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
        _logger.info("page switch → %s", tab_id)
        if tab_id == "search":
            if self._current_tab == "search" and self._search_query:
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
            self._current_tab = tab_id
            self._nav_stack.clear()
            self._load_view(tab_id)

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        self.query_one("#detail-panel", DetailPanel).clear()
        self._stream_view(view)

    # ── Streaming workers ─────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="feed_loader")
    def _scheduled_home_refresh(self) -> None:
        """Silently refresh the home feed in the background every 10 minutes."""
        import src.ytdlp as ytdlp

        # 1. Trigger the loading animation
        self.app.call_from_thread(self.query_one(AppHeader).set_status_loading)

        app = self.app
        config = app.config
        cache = app.cache
        try:
            for _ in ytdlp.stream_flat(
                ytdlp.FEED_URLS["home"], config, cache, feed_key="home"
            ):
                pass
            self.app.call_from_thread(
                self._log, "[green]Background home feed refresh complete.[/green]"
            )

            # 2. Success! Hide the animation
            self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)

        except Exception as e:
            self.app.call_from_thread(
                self._log, f"[red]Background refresh failed: {e}[/red]"
            )

            # 3. Fail! Show the dead animation
            self.app.call_from_thread(self.query_one(AppHeader).set_status_error)

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str) -> None:
        panel = self.query_one("#video-list-panel", VideoListPanel)

        self.app.call_from_thread(self.query_one(AppHeader).set_status_loading)

        app = self.app
        config = app.config
        cache = app.cache

        # sync_handled: True when the sub-method already called finish_loading
        sync_handled = False
        try:
            if view in ("home", "subscriptions"):
                import src.ytdlp as ytdlp

                self._stream_feed(view, panel, config, cache, ytdlp)
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
                self._load_playlist_videos_sync(view[len("playlist:") :], panel, cache)
                sync_handled = True
        except Exception as exc:
            msg = str(exc)
            self.app.call_from_thread(panel.set_error_message, f"⚠ {msg}")
            self.app.call_from_thread(self._log, f"[red]Error in {view}: {msg}[/red]")
            self.app.call_from_thread(self.query_one(AppHeader).set_status_error)
            return

        self.app.call_from_thread(self.query_one(AppHeader).set_status_idle)
        if not sync_handled:
            self.app.call_from_thread(panel.finish_loading)

    def _make_enrich_callback(self, panel):
        app = self.app
        screen = self

        def _on_done(vid: str, entry: dict) -> None:
            app.call_from_thread(panel.update_entry_by_id, vid, entry)
            app.call_from_thread(screen._maybe_refresh_detail, vid, entry)

        return _on_done

    def _maybe_refresh_detail(self, vid: str, entry: dict) -> None:
        try:
            self.query_one("#detail-panel", DetailPanel).refresh_metadata(entry)
        except Exception:
            pass

    def _stream_feed(self, feed_key: str, panel, config, cache, ytdlp) -> None:
        """Stream a home/subscriptions feed into panel, prioritizing the disk cache."""
        is_suppressed = cache.is_suppressed

        cached_ids = cache.get_feed(feed_key) or cache.get_feed_stale(feed_key)

        if cached_ids and len(cached_ids) >= _MIN_FEED_COUNT:
            count = 0
            for vid_id in cached_ids:
                if feed_key == "home" and is_suppressed(vid_id):
                    continue
                entry = cache.get_video_raw(vid_id)
                if entry:
                    self.app.call_from_thread(panel.append_entry, entry)
                    count += 1

            if count >= _MIN_FEED_COUNT:
                self._log(f"[dim]{feed_key}: {count} from cache, refreshing…[/dim]")

                self.app.call_from_thread(
                    self.notify,
                    f"Loaded from cache — refreshing in background…",
                    timeout=3,
                )
                self._background_refresh_worker(feed_key)
                return

        cache.clear_feed(feed_key)
        gen = ytdlp.stream_flat(
            ytdlp.FEED_URLS[feed_key], config, cache, feed_key=feed_key
        )
        for entry in gen:
            vid_id = entry.get("id")
            if feed_key == "home" and vid_id and is_suppressed(vid_id):
                continue
            self.app.call_from_thread(panel.append_entry, entry)

    @work(thread=True, group="bg_refresh")
    def _background_refresh_worker(self, feed_key: str) -> None:
        """Silently refetch a feed in the background after serving stale cache."""
        import src.ytdlp as ytdlp

        try:
            self.app.cache.clear_feed(feed_key)
            for _ in ytdlp.stream_flat(
                ytdlp.FEED_URLS[feed_key],
                self.app.config,
                self.app.cache,
                feed_key=feed_key,
            ):
                pass
        except Exception as exc:
            self.app.call_from_thread(
                self._log, f"[dim]Background refresh failed: {exc}[/dim]"
            )

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
        self.query_one("#detail-panel", DetailPanel).update_entry(message.entry)
        self._refresh_queue_hint(message.entry)

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

    # ── Batch Lazy Loading Intercept ──────────────────────────────────────────

    def on_video_list_panel_batch_revealed(
        self, message: VideoListPanel.BatchRevealed
    ) -> None:
        if self._current_tab in (
            "home",
            "subscriptions",
            "search",
        ) or self._current_tab.startswith("playlist:"):
            import src.ytdlp as ytdlp

            ids = [
                e.get("id")
                for e in message.entries
                if e.get("id") and not e.get("id").startswith("__")
            ]
            if ids:
                ytdlp.enrich_in_background(
                    ids,
                    self.app.config,
                    self.app.cache,
                    on_done=self._make_enrich_callback(
                        self.query_one("#video-list-panel", VideoListPanel)
                    ),
                )

    # ── Video action menu (Enter) ─────────────────────────────────────────────

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
            tabs = self.query_one("#nav-tabs", Tabs)
            if not query:
                _logger.debug("search dialog cancelled")
                tabs.active = self._current_tab
                return
            _logger.info("search query: %r", query)
            self._search_query = query
            self._current_tab = "search"
            self._nav_stack.clear()
            for tab in tabs.query(Tab):
                if tab.id == "search":
                    tab.label = f"🔍 {query[:20]}"
                    break
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
        app = self.app  # type: ignore[attr-defined]
        if self._current_tab in ("home", "subscriptions"):
            app.cache.clear_feed(self._current_tab)
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
        self._stop_audio()
        try:
            import src.ytdlp as ytdlp

            ytdlp.kill_all_active()
        except Exception:
            pass
        threading.Timer(0.6, os._exit, args=(0,)).start()
        self.app.exit()
