"""MainScreen — primary TUI screen with nav tabs, video list, and detail panel."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static, Tab, Tabs

from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

if TYPE_CHECKING:
    pass


# ── Tab definitions ────────────────────────────────────────────────────────────

_TABS = [
    ("home",          "🏠 Home"),
    ("subscriptions", "📺 Subscriptions"),
    ("search",        "🔍 Search"),
    ("history",       "🕐 History"),
    ("library",       "📁 Library"),
    ("playlists",     "🎵 Playlists"),
]

_MIN_FEED_COUNT = 15


class MainScreen(Screen):
    """
    Primary screen with:
      - Nav tabs across the top (Home / Subs / Search / History / Library / Playlists)
      - VideoListPanel (left, 45%) — streams entries, j/k navigation
      - DetailPanel (right, 55%) — thumbnail + metadata + action hints
      - Optional debug log panel at bottom (toggle with ?)
      - Footer with key hints
    """

    BINDINGS = [
        # Navigation
        Binding("j",          "cursor_down",    "Down",      show=False),
        Binding("k",          "cursor_up",      "Up",        show=False),
        Binding("g",          "cursor_top",     "Top",       show=False),
        Binding("G",          "cursor_bottom",  "Bottom",    show=False),
        Binding("backspace",  "nav_back",       "Back",      show=False),
        # Playback
        Binding("enter",      "activate",       "Open",      show=False),
        Binding("w",          "watch",          "Watch",     show=True),
        Binding("W",          "watch_quality",  "Quality ▶", show=False),
        Binding("l",          "listen",         "Listen",    show=True),
        Binding("L",          "listen_quality", "Quality ♪", show=False),
        # Download
        Binding("d",          "dl_video",       "DL Video",  show=False),
        Binding("a",          "dl_audio",       "DL Audio",  show=False),
        # Other
        Binding("s",          "subscribe",      "Subscribe", show=False),
        Binding("p",          "playlist",       "Playlist",  show=False),
        Binding("b",          "browser",        "Browser",   show=False),
        # App
        Binding("/",          "search",         "Search",    show=True),
        Binding("r",          "refresh",        "Refresh",   show=True),
        Binding("?",          "toggle_log",     "Debug",     show=False),
        Binding("q",          "quit_app",       "Quit",      show=True),
        # Tab shortcuts
        Binding("1",          "tab_home",       show=False),
        Binding("2",          "tab_subs",       show=False),
        Binding("3",          "tab_search",     show=False),
        Binding("4",          "tab_history",    show=False),
        Binding("5",          "tab_library",    show=False),
        Binding("6",          "tab_playlists",  show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_tab = "home"
        self._search_query: str = ""
        # Playlist nav stack: list of view names to go back to
        self._nav_stack: list[str] = []
        self._log_visible = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tabs(
            *[Tab(label, id=tid) for tid, label in _TABS],
            id="nav-tabs",
        )
        with Horizontal(id="main-content"):
            yield VideoListPanel(id="video-list-panel")
            yield DetailPanel(id="detail-panel")
        yield RichLog(
            id="debug-log",
            highlight=True,
            markup=True,
            max_lines=100,
            wrap=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        # Hide debug log by default
        self.query_one("#debug-log").display = False
        self._load_view("home")

    # ── Tab switching ─────────────────────────────────────────────────────────

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if not event.tab or not event.tab.id:
            return
        tab_id = event.tab.id
        if tab_id == "search":
            if self._current_tab == "search" and self._search_query:
                # Already showing search results — stay, don't reopen dialog
                pass
            else:
                self._open_search_dialog()
        else:
            self._current_tab = tab_id
            self._nav_stack.clear()
            self._load_view(tab_id)

    def _load_view(self, view: str) -> None:
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        self.query_one("#detail-panel", DetailPanel).clear()
        self._stream_view(view)

    # ── Streaming workers ─────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str) -> None:
        panel = self.query_one("#video-list-panel", VideoListPanel)
        app = self.app  # type: ignore[attr-defined]
        config = app.config
        cache = app.cache
        collected_ids: list[str] = []

        try:
            if view in ("home", "subscriptions"):
                import src.ytdlp as ytdlp
                self._stream_feed(view, panel, config, cache, ytdlp, collected_ids)
                return

            elif view == "search":
                if not self._search_query:
                    self.call_from_thread(panel.set_empty_message, "Press / to search")
                    return
                import src.ytdlp as ytdlp
                gen = ytdlp.stream_search(self._search_query, config, cache)
                for entry in gen:
                    self.call_from_thread(panel.append_entry, entry)
                    vid = entry.get("id")
                    if vid:
                        collected_ids.append(vid)

            elif view == "history":
                from src import history as hist
                for entry in hist.iter_entries():
                    self.call_from_thread(panel.append_entry, entry)

            elif view == "library":
                from src import library as lib
                entries = lib.all_entries(config.video_dir, config.audio_dir)
                for entry in entries:
                    self.call_from_thread(panel.append_entry, entry)

            elif view == "playlists":
                self._load_playlists_sync(panel)
                return

            elif view.startswith("playlist:"):
                name = view[len("playlist:"):]
                self._load_playlist_videos_sync(name, panel, cache)
                return

        except Exception as exc:
            import traceback
            msg = str(exc)
            self.call_from_thread(panel.set_error_message, f"⚠ {msg}")
            self.call_from_thread(self._log, f"[red]Error in {view}: {msg}[/red]")
            return

        self.call_from_thread(panel.finish_loading)

        # Background enrichment for feeds/search
        if collected_ids and view in ("home", "subscriptions", "search"):
            import src.ytdlp as ytdlp
            ytdlp.enrich_in_background(collected_ids[:15], config, cache)

    def _stream_feed(self, feed_key: str, panel, config, cache, ytdlp, collected_ids: list) -> None:
        """
        Stale-while-revalidate: serve stale cache instantly, then background-
        refresh so the *next* visit gets fresh data. Falls through to network
        fetch when no cache exists at all.
        """
        fresh_ids = cache.get_feed(feed_key)  # None if expired / missing

        if fresh_ids is None:
            # Try serving stale data immediately
            stale_ids = cache.get_feed_stale(feed_key)
            if stale_ids and len(stale_ids) >= _MIN_FEED_COUNT:
                count = 0
                for vid_id in stale_ids:
                    entry = cache.get_video_raw(vid_id)
                    if entry:
                        self.call_from_thread(panel.append_entry, entry)
                        collected_ids.append(vid_id)
                        count += 1
                if count >= _MIN_FEED_COUNT:
                    self.call_from_thread(panel.finish_loading)
                    self.call_from_thread(
                        self.notify,
                        "Showing cached results — refreshing in background…",
                        timeout=3,
                    )
                    # Kick off silent background refresh for next visit
                    t = threading.Thread(
                        target=self._background_refresh,
                        args=(feed_key, ytdlp, config, cache),
                        daemon=True,
                    )
                    t.start()
                    if collected_ids:
                        ytdlp.enrich_in_background(collected_ids[:15], config, cache)
                    return
                # Not enough video JSONs on disk — fall through to network
                cache.clear_feed(feed_key)

        # Network fetch (also used when fresh cache exists — stream_flat handles that)
        gen = ytdlp.stream_flat(
            ytdlp.FEED_URLS[feed_key], config, cache, feed_key=feed_key
        )
        for entry in gen:
            self.call_from_thread(panel.append_entry, entry)
            vid = entry.get("id")
            if vid:
                collected_ids.append(vid)
        self.call_from_thread(panel.finish_loading)
        if collected_ids:
            ytdlp.enrich_in_background(collected_ids[:15], config, cache)

    @staticmethod
    def _background_refresh(feed_key: str, ytdlp, config, cache) -> None:
        """Silently re-fetch a feed so the next visit is instant. Runs in daemon thread."""
        try:
            # stream_flat will detect stale cache and do a fresh network fetch
            cache.clear_feed(feed_key)
            for _ in ytdlp.stream_flat(
                ytdlp.FEED_URLS[feed_key], config, cache, feed_key=feed_key
            ):
                pass
        except Exception:
            pass  # Silent failure — stale data remains for next visit

    def _load_playlists_sync(self, panel) -> None:
        from src import playlist
        names = playlist.list_names()
        if not names:
            self.call_from_thread(
                panel.set_empty_message, "No playlists. Select a video and press p."
            )
            return
        for name in names:
            ids = playlist.get_playlist(name)
            entry = {
                "id": f"__playlist__{name}",
                "title": f"🎵  {name}",
                "uploader": f"{len(ids)} video{'s' if len(ids) != 1 else ''}",
                "duration": None,
                "view_count": None,
                "_is_playlist": True,
                "_playlist_name": name,
            }
            self.call_from_thread(panel.append_entry, entry)
        self.call_from_thread(panel.finish_loading)

    def _load_playlist_videos_sync(self, name: str, panel, cache) -> None:
        from src import playlist
        ids = playlist.get_playlist(name)
        if not ids:
            self.call_from_thread(panel.set_empty_message, f'Playlist "{name}" is empty.')
            return
        for vid_id in ids:
            entry = cache.get_video_raw(vid_id)
            if not entry:
                entry = {
                    "id": vid_id,
                    "title": vid_id,
                    "uploader": "",
                }
            self.call_from_thread(panel.append_entry, entry)
        self.call_from_thread(panel.finish_loading)

    # ── Search ────────────────────────────────────────────────────────────────

    def action_search(self) -> None:
        self._open_search_dialog()

    def _open_search_dialog(self) -> None:
        from src.tui.screens.search_modal import SearchModal

        def on_result(query: str | None) -> None:
            tabs = self.query_one("#nav-tabs", Tabs)
            if not query:
                # Cancelled — return to previous tab
                tabs.active = self._current_tab
                return
            self._search_query = query
            self._current_tab = "search"
            self._nav_stack.clear()
            # Update search tab label
            for tab in tabs.query(Tab):
                if tab.id == "search":
                    tab.label = f"🔍 {query[:20]}"
                    break
            tabs.active = "search"
            self._load_view("search")

        self.app.push_screen(SearchModal(), on_result)

    # ── Playlist navigation ───────────────────────────────────────────────────

    def _open_playlist(self, name: str) -> None:
        """Drill into a playlist's videos. Saves current view to nav stack."""
        self._nav_stack.append(self._current_tab)
        self._current_tab = f"playlist:{name}"
        panel = self.query_one("#video-list-panel", VideoListPanel)
        panel.clear_and_set_loading()
        panel.set_breadcrumb(f"🎵 {name}  ← backspace to go back")
        self.query_one("#detail-panel", DetailPanel).clear()
        self._stream_view(f"playlist:{name}")

    def action_nav_back(self) -> None:
        """Pop nav stack and return to the previous view."""
        if not self._nav_stack:
            return
        prev = self._nav_stack.pop()
        self._current_tab = prev
        tabs = self.query_one("#nav-tabs", Tabs)
        if prev in ("home", "subscriptions", "history", "library", "playlists"):
            tabs.active = prev  # triggers on_tabs_tab_activated → _load_view
        elif prev == "search":
            self._load_view("search")

    # ── Video actions ─────────────────────────────────────────────────────────

    def _selected_entry(self) -> dict | None:
        return self.query_one("#video-list-panel", VideoListPanel).selected_entry

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        if entry.get("_is_playlist"):
            self._open_playlist(entry.get("_playlist_name", ""))
        else:
            self.action_watch()

    # ── Playback ──────────────────────────────────────────────────────────────

    def action_watch(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        self._play(entry, audio_only=False)

    def action_watch_quality(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                self._play(entry, audio_only=False, ytdl_format=fmt)

        self.app.push_screen(QualityModal(audio_only=False), on_fmt)

    def action_listen(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        self._play(entry, audio_only=True)

    def action_listen_quality(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                self._play(entry, audio_only=True, ytdl_format=fmt)

        self.app.push_screen(QualityModal(audio_only=True), on_fmt)

    @work(exclusive=True, group="player")
    async def _play(
        self,
        entry: dict,
        *,
        audio_only: bool,
        ytdl_format: str = "",
    ) -> None:
        """
        Async worker: suspends the TUI, runs mpv in a thread, then resumes.
        Using an async (not thread) worker so self.app.suspend() is called on
        the event loop thread, which is required for correct terminal handling.
        """
        import asyncio
        from src import history, player

        app = self.app  # type: ignore[attr-defined]
        vid = entry.get("id", "")
        url: str = entry.get("_local_path") or f"https://www.youtube.com/watch?v={vid}"
        title: str = entry.get("title", "")
        cookie_args = app.config.cookie_args
        fmt = ytdl_format or ""

        self._log(f"Playing: [bold]{title[:60]}[/bold]")

        with self.app.suspend():
            await asyncio.to_thread(
                player.play,
                url,
                audio_only=audio_only,
                title=title,
                ytdl_format=fmt,
                cookie_args=cookie_args,
            )

        history.add(entry)
        self.notify(f"✓ Finished: {title[:50]}", timeout=4)

    # ── Download ──────────────────────────────────────────────────────────────

    def action_dl_video(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        self._open_download(entry, audio_only=False)

    def action_dl_audio(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        self._open_download(entry, audio_only=True)

    def _open_download(self, entry: dict, *, audio_only: bool) -> None:
        from src.tui.screens.download_modal import DownloadModal

        vid = entry.get("id", "")
        mode = "audio" if audio_only else "video"
        title = entry.get("title", vid)

        def on_done(success: bool | None) -> None:
            if success:
                self.notify(f"✓ Downloaded {mode}: {title[:40]}", timeout=5)
                self._log(f"[green]Downloaded {mode}: {title[:60]}[/green]")
            else:
                self.notify("✗ Download failed or cancelled", severity="warning", timeout=4)

        self.app.push_screen(DownloadModal(vid, entry, audio_only=audio_only), on_done)

    # ── Subscribe ─────────────────────────────────────────────────────────────

    def action_subscribe(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        url = (
            entry.get("channel_url")
            or entry.get("uploader_url")
        )
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

    # ── Playlist management ───────────────────────────────────────────────────

    def action_playlist(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.playlist_modal import PlaylistModal

        def on_done(_: None) -> None:
            detail = self.query_one("#detail-panel", DetailPanel)
            detail._update_playlists(entry.get("id", ""))

        self.app.push_screen(PlaylistModal(entry), on_done)

    # ── Browser ───────────────────────────────────────────────────────────────

    def action_browser(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        if vid and not vid.startswith("__"):
            import webbrowser
            webbrowser.open(f"https://www.youtube.com/watch?v={vid}")
            self.notify("Opened in browser")

    # ── Navigation ────────────────────────────────────────────────────────────

    def action_cursor_down(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_up()

    def action_cursor_top(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_to_top()

    def action_cursor_bottom(self) -> None:
        self.query_one("#video-list-panel", VideoListPanel).cursor_to_bottom()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        app = self.app  # type: ignore[attr-defined]
        if self._current_tab in ("home", "subscriptions"):
            app.cache.clear_feed(self._current_tab)
        self._load_view(self._current_tab)
        self.notify(f"Refreshing {self._current_tab}…", timeout=2)

    # ── Debug log toggle ──────────────────────────────────────────────────────

    def action_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        log = self.query_one("#debug-log")
        log.display = self._log_visible
        if self._log_visible:
            self.notify("Debug log visible — press ? to hide", timeout=2)

    def _log(self, msg: str) -> None:
        """Write a line to the in-TUI debug log."""
        try:
            log = self.query_one("#debug-log", RichLog)
            log.write(msg)
        except Exception:
            pass

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

    # ── Quit ──────────────────────────────────────────────────────────────────

    def action_quit_app(self) -> None:
        self.app.exit()

    # ── Detail panel updates ──────────────────────────────────────────────────

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        self.query_one("#detail-panel", DetailPanel).update_entry(message.entry)

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()
