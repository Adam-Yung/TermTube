"""ChannelScreen — full-screen channel browser with 3-column layout.

Layout: ChannelInfoPanel (left) | VideoList + Tabs (center) | DetailPanel + ActionBar (right)
"""

from __future__ import annotations

import re
import subprocess
from collections import OrderedDict

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Static, Tab, Tabs

from src import logger as _logger
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel
from src.tui.widgets.thumbnail_widget import ThumbnailWidget

_PAGE_SIZE = 20
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")
_FOCUS_DWELL_S = 0.10
_THUMB_DWELL_S = 0.15
_CHAFA_RAM_CACHE_MAX = 64


def _safe_ch_id(info: dict) -> str:
    raw = info.get("channel_id") or info.get("uploader_id") or ""
    if not raw:
        raw = _SAFE_ID_RE.sub("_", info.get("channel_url", "")[:60])
    return "ch_" + raw[:50]


def _fmt_subs(n) -> str:
    if n is None:
        return ""
    if n >= 1_000_000:
        return str(round(n * 1e-6, 1)) + "M"
    if n >= 1_000:
        return str(int(n // 1_000)) + "K"
    return str(n)


class ChannelInfoPanel(Vertical):
    """Narrow left panel showing channel avatar, name, subs, description."""

    def compose(self) -> ComposeResult:
        yield ThumbnailWidget(id="ch-thumbnail")
        yield Static("", id="ch-name", markup=True)
        yield Static("", id="ch-subs", markup=True)
        yield Static("", id="ch-url", markup=True)
        yield Static("", id="ch-sep", markup=False)
        with ScrollableContainer(id="ch-desc-scroll"):
            yield Static("", id="ch-desc", markup=False)

    def show_loading(self) -> None:
        self.query_one("#ch-name", Static).update("Loading...")
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_loading()

    def set_thumbnail_image(self, ch_id: str, path) -> None:
        tw = self.query_one("#ch-thumbnail", ThumbnailWidget)
        tw.set_image_path(ch_id, path)

    def set_thumbnail_ansi(self, ch_id: str, ansi: str) -> None:
        tw = self.query_one("#ch-thumbnail", ThumbnailWidget)
        tw.set_ansi(ch_id, ansi)

    def update_info(self, info: dict) -> None:
        name = info.get("channel", "") or info.get("uploader", "")
        subs = _fmt_subs(info.get("subscriber_count"))
        url = info.get("channel_url", "") or info.get("uploader_url", "")
        desc = (info.get("description", "") or "No description.")[:2000]
        self.query_one("#ch-name", Static).update(f"[bold white]{name}[/bold white]")
        self.query_one("#ch-subs", Static).update(f"[dim]{subs}[/dim]" if subs else "")
        self.query_one("#ch-url", Static).update(f"[dim]{url[:50]}[/dim]" if url else "")
        self.query_one("#ch-sep", Static).update(chr(9472) * 24)
        self.query_one("#ch-desc", Static).update(desc)


class ChannelScreen(Screen):
    """Full-screen channel browser: info left, video list center, detail right."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("backspace", "go_back", "Back", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("left_square_bracket", "page_prev", "Prev", show=False),
        Binding("right_square_bracket", "page_next", "Next", show=False),
        Binding("g", "page_first", show=False),
        Binding("G", "page_last", show=False),
        Binding("s", "sort_picker", "Sort", show=True),
        Binding("r", "reload", "Reload", show=True),
        Binding("enter", "activate", "Actions", show=False),
        Binding("w", "watch", show=False),
        Binding("l", "listen", show=False),
        Binding("d", "download", show=False),
        Binding("y", "copy_url", show=False),
        Binding("b", "browser", show=False),
        Binding("grave_accent", "tab_picker", "Pages", show=False),
    ]

    def __init__(self, channel_url: str, channel_name: str = "") -> None:
        super().__init__()
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._current_tab: str = "ch-tab-videos"
        self._sort: str = "date"
        self._info_proc: subprocess.Popen | None = None
        self._content_proc: subprocess.Popen | None = None
        self._active_workers: int = 0
        self._video_panel: VideoListPanel | None = None
        self._thumb_session: int = 0
        self._content_session: int = 0
        self._initial_load_done: bool = False
        # Detail panel focus/thumb workers
        self._focus_dwell_timer: Timer | None = None
        self._thumb_dwell_timer: Timer | None = None
        self._focus_proc: subprocess.Popen | None = None
        self._thumb_proc: subprocess.Popen | None = None
        self._focus_session: int = 0
        self._detail_thumb_session: int = 0
        self._last_focus_id: str = ""
        self._chafa_ram_cache: OrderedDict[tuple[str, int, int, str], str] = OrderedDict()

    def compose(self) -> ComposeResult:
        with Horizontal(id="ch-main"):
            yield ChannelInfoPanel(id="ch-info-panel")
            with Vertical(id="ch-center"):
                yield Tabs(
                    Tab("Videos", id="ch-tab-videos"),
                    Tab("Playlists", id="ch-tab-playlists"),
                    id="ch-tabs",
                )
                yield VideoListPanel(id="ch-video-list")
            yield DetailPanel(id="ch-detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._video_panel = self.query_one("#ch-video-list", VideoListPanel)
        self.query_one("#ch-info-panel", ChannelInfoPanel).show_loading()
        self._video_panel.clear_and_set_loading()
        self._video_panel.focus()
        tabs = self.query_one("#ch-tabs", Tabs)
        tabs.can_focus = False
        for tab in tabs.query(Tab):
            tab.can_focus = False
        self._load_channel_info()
        self.set_timer(0.15, self._ensure_content_loaded)

    def _ensure_content_loaded(self) -> None:
        if not self._initial_load_done:
            self._start_content_load()

    def _start_content_load(self) -> None:
        self._initial_load_done = True
        if self._video_panel is None:
            return
        self._content_session += 1
        self._video_panel.clear_and_set_loading()
        tab = "playlists" if self._current_tab == "ch-tab-playlists" else "videos"
        self._load_content(tab, self._sort, self._content_session)

    # ── Channel info worker ───────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="ch_info")
    def _load_channel_info(self) -> None:
        import src.ytdlp as ytdlp
        try:
            def _on_proc(p: subprocess.Popen) -> None:
                self._info_proc = p
            info = ytdlp.fetch_channel_info(
                self._channel_url, self.app.config, self.app.cache,
                on_proc_started=_on_proc,
            )
            if info:
                self.app.call_from_thread(self._apply_info, info)
            else:
                self.app.call_from_thread(self._show_info_error)
        except Exception as exc:
            _logger.debug("channel info error: %s", exc)
            self.app.call_from_thread(self._show_info_error)

    # ── Content worker ────────────────────────────────────────────────────────

    @work(thread=True, group="ch_content")
    def _load_content(self, tab: str, sort: str, session: int) -> None:
        import src.ytdlp as ytdlp
        panel = self._video_panel
        if panel is None:
            return
        try:
            def _on_proc(p: subprocess.Popen) -> None:
                self._content_proc = p
            if tab == "playlists":
                entries = ytdlp.fetch_channel_playlists(
                    self._channel_url, self.app.config, self.app.cache,
                    on_proc_started=_on_proc,
                )
            else:
                entries = ytdlp.fetch_channel_videos(
                    self._channel_url, self.app.config, self.app.cache,
                    sort=sort, on_proc_started=_on_proc,
                )
            _logger.debug("channel tab=%s entries=%d", tab, len(entries))
            if session != self._content_session:
                return
            if not entries:
                self.app.call_from_thread(panel.set_empty_message, "No content found.")
                return
            idx2 = 0
            pnum = 1
            while idx2 < len(entries):
                chunk = entries[idx2:idx2 + _PAGE_SIZE]
                self.app.call_from_thread(panel.add_page, pnum, chunk)
                idx2 += _PAGE_SIZE
                pnum += 1
            if session != self._content_session:
                return
            self.app.call_from_thread(panel.load_page, 1)
            self.app.call_from_thread(panel.finish_loading)
        except Exception as exc:
            _logger.debug("channel content error: %s", exc)
            if session == self._content_session:
                self.app.call_from_thread(panel.set_error_message, str(exc))

    # ── Channel thumbnail ─────────────────────────────────────────────────────

    def _apply_info(self, info: dict) -> None:
        try:
            panel = self.query_one("#ch-info-panel", ChannelInfoPanel)
            panel.update_info(info)
        except Exception:
            pass
        thumb_url = info.get("thumbnail", "")
        ch_id = _safe_ch_id(info)
        if thumb_url and ch_id:
            try:
                tw = self.query_one("#ch-info-panel #ch-thumbnail", ThumbnailWidget)
                tw.set_video_id(ch_id)
                tw.set_loading()
            except Exception:
                pass
            self._thumb_session += 1
            self._fetch_channel_thumb(ch_id, thumb_url, self._thumb_session)
        else:
            self._set_thumb_placeholder()

    def _set_thumb_placeholder(self) -> None:
        try:
            self.query_one("#ch-info-panel #ch-thumbnail", ThumbnailWidget).set_placeholder()
        except Exception:
            pass

    @work(thread=True, exclusive=True, group="ch_thumb")
    def _fetch_channel_thumb(self, ch_id: str, url: str, session: int) -> None:
        from src.ui import thumbnail as thumb_mod
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE
        if _HAS_TEXTUAL_IMAGE:
            local = thumb_mod._thumb_path(ch_id)
            if not local.exists():
                local = thumb_mod.download(ch_id, url) or local
            if session != self._thumb_session:
                return
            if local and local.exists():
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(local) as _img:
                        _img.load()
                except Exception:
                    self.app.call_from_thread(self._set_thumb_placeholder)
                    return
                if session != self._thumb_session:
                    return
                _local = local
                self.app.call_from_thread(
                    lambda: self.query_one("#ch-info-panel", ChannelInfoPanel).set_thumbnail_image(ch_id, _local)
                )
            else:
                self.app.call_from_thread(self._set_thumb_placeholder)
        else:
            local = thumb_mod._thumb_path(ch_id)
            if not local.exists():
                local = thumb_mod.download(ch_id, url) or local
            if session != self._thumb_session:
                return
            if not (local and local.exists()):
                self.app.call_from_thread(self._set_thumb_placeholder)
                return
            ansi = thumb_mod.render(ch_id, {"id": ch_id, "thumbnail": url}) or ""
            if session != self._thumb_session:
                return
            if ansi:
                _id2, _ansi = ch_id, ansi
                self.app.call_from_thread(
                    lambda: self.query_one("#ch-info-panel", ChannelInfoPanel).set_thumbnail_ansi(_id2, _ansi)
                )
            else:
                self.app.call_from_thread(self._set_thumb_placeholder)

    def _show_info_error(self) -> None:
        try:
            panel = self.query_one("#ch-info-panel", ChannelInfoPanel)
            panel.query_one("#ch-name", Static).update("Could not load channel info.")
        except Exception:
            pass

    # ── Tab switching ─────────────────────────────────────────────────────────

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        if not tab_id:
            return
        if tab_id == self._current_tab and self._initial_load_done:
            return
        self._current_tab = tab_id
        self._cancel_content_proc()
        self._start_content_load()

    def _cancel_content_proc(self) -> None:
        if self._content_proc and self._content_proc.poll() is None:
            try:
                self._content_proc.terminate()
            except Exception:
                pass
        self._content_proc = None

    # ── Detail panel focus/thumbnail workers ──────────────────────────────────

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        entry = message.entry
        vid = entry.get("id", "")
        detail = self.query_one("#ch-detail-panel", DetailPanel)
        detail.update_basic(entry)
        self._cancel_pending_focus_and_thumb()
        self._last_focus_id = vid
        if vid and not vid.startswith("__"):
            detail.set_thumbnail_video_id(vid)
            from src.ui.thumbnail import _thumb_path
            if not _thumb_path(vid).exists():
                detail.set_thumbnail_loading()
            self._thumb_dwell_timer = self.set_timer(
                _THUMB_DWELL_S, lambda: self._kick_thumb(vid, entry)
            )
            self._focus_dwell_timer = self.set_timer(
                _FOCUS_DWELL_S, lambda: self._kick_focus(vid, entry)
            )

    def _cancel_pending_focus_and_thumb(self) -> None:
        if self._focus_dwell_timer is not None:
            self._focus_dwell_timer.stop()
            self._focus_dwell_timer = None
        if self._thumb_dwell_timer is not None:
            self._thumb_dwell_timer.stop()
            self._thumb_dwell_timer = None
        self._focus_session += 1
        self._detail_thumb_session += 1
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

    def _kick_thumb(self, vid: str, entry: dict) -> None:
        self._thumb_dwell_timer = None
        try:
            if self.query_one("#ch-detail-panel", DetailPanel).current_id != vid:
                return
        except Exception:
            return
        self._detail_thumb_session += 1
        session = self._detail_thumb_session
        self._thumb_worker(vid, entry, session)

    def _kick_focus(self, vid: str, entry: dict) -> None:
        self._focus_dwell_timer = None
        try:
            if self.query_one("#ch-detail-panel", DetailPanel).current_id != vid:
                return
        except Exception:
            return
        if entry.get("description"):
            return
        self._focus_session += 1
        session = self._focus_session
        self._focus_worker(vid, entry, session)

    @work(thread=True, exclusive=True, group="ch_detail_focus")
    def _focus_worker(self, vid: str, entry: dict, session: int) -> None:
        import src.ytdlp as ytdlp

        def _on_proc(p: subprocess.Popen) -> None:
            self._focus_proc = p

        try:
            full = ytdlp.fetch_full(
                vid, self.app.config, self.app.cache, on_proc_started=_on_proc
            )
        except Exception:
            return
        finally:
            self._focus_proc = None

        if full is None or session != self._focus_session:
            return
        try:
            panel = self.query_one("#ch-video-list", VideoListPanel)
            self.app.call_from_thread(panel.update_entry_by_id, vid, full)
            self.app.call_from_thread(
                self.query_one("#ch-detail-panel", DetailPanel).refresh_metadata, full
            )
        except Exception:
            pass

    @work(thread=True, exclusive=True, group="ch_detail_thumb")
    def _thumb_worker(self, vid: str, entry: dict, session: int) -> None:
        from src.ui import thumbnail as thumb_mod
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        detail = self.query_one("#ch-detail-panel", DetailPanel)

        if _HAS_TEXTUAL_IMAGE:
            local = thumb_mod._thumb_path(vid)
            if not local.exists():
                url = thumb_mod._best_thumb_url(entry)
                if url:
                    local = thumb_mod.download(vid, url) or local
            if session != self._detail_thumb_session:
                return
            if local and local.exists():
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(local) as _pil_img:
                        _pil_img.load()
                except Exception:
                    self.app.call_from_thread(detail.set_thumbnail_placeholder)
                    return
                if session != self._detail_thumb_session:
                    return
                self.app.call_from_thread(detail.set_thumbnail_image, vid, local)
            else:
                self.app.call_from_thread(detail.set_thumbnail_placeholder)
            return

        # chafa branch
        try:
            thumb_widget = detail.query_one("#thumbnail")
            cols = thumb_widget.size.width if thumb_widget.size.width > 0 else 38
            rows = thumb_widget.size.height if thumb_widget.size.height > 0 else 20
        except Exception:
            cols, rows = 38, 20

        config = getattr(self.app, "config", None)
        fmt = thumb_mod._chafa_format_for_tui(config)
        cache_key_fmt = "ascii" if fmt == "ascii" else "symbols"
        ram_key = (vid, cols, rows, cache_key_fmt)

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

        if session != self._detail_thumb_session:
            return

        if ansi:
            self._chafa_ram_cache[ram_key] = ansi
            if len(self._chafa_ram_cache) > _CHAFA_RAM_CACHE_MAX:
                self._chafa_ram_cache.popitem(last=False)
            self.app.call_from_thread(detail.set_thumbnail_ansi, vid, ansi)
        else:
            self.app.call_from_thread(detail.set_thumbnail_placeholder)

    def on_detail_panel_rerender_requested(
        self, message: DetailPanel.RerenderRequested
    ) -> None:
        entry = message.entry
        vid = entry.get("id", "")
        if vid and not vid.startswith("__"):
            self._kick_thumb(vid, entry)

    def on_detail_panel_channel_clicked(
        self, message: DetailPanel.ChannelClicked
    ) -> None:
        pass  # Already on the channel screen

    # ── Actions ───────────────────────────────────────────────────────────────

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        from src.tui.screens.video_action_modal import VideoActionModal

        def on_action(key: str | None) -> None:
            if not key:
                return
            dispatch = {
                "watch": lambda: self.action_watch(),
                "watch_quality": lambda: self._watch_quality(entry),
                "listen": lambda: self._start_listen(entry),
                "listen_quality": lambda: self._listen_quality(entry),
                "download": lambda: self.action_download(),
                "channel": lambda: None,
                "copy_url": lambda: self.action_copy_url(),
                "playlist": lambda: None,
                "browser": lambda: self.action_browser(),
            }
            fn = dispatch.get(key)
            if fn:
                fn()

        self.app.push_screen(VideoActionModal(entry), on_action)

    def action_channel(self) -> None:
        pass  # Already on the channel screen

    def action_watch(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.watch_modal import WatchModal
        self.app.push_screen(WatchModal(entry))

    def action_listen(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        self._start_listen(entry)

    def _start_listen(self, entry: dict) -> None:
        from src.tui.screens.main_screen import MainScreen
        for screen in self.app.screen_stack:
            if isinstance(screen, MainScreen):
                screen._start_audio(entry)
                return

    def _listen_quality(self, entry: dict) -> None:
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                self._start_listen_with_format(entry, fmt)

        self.app.push_screen(QualityModal(audio_only=True), on_fmt)

    def _start_listen_with_format(self, entry: dict, fmt: str) -> None:
        from src.tui.screens.main_screen import MainScreen
        for screen in self.app.screen_stack:
            if isinstance(screen, MainScreen):
                screen._start_audio(entry, ytdl_format=fmt)
                return

    def _watch_quality(self, entry: dict) -> None:
        from src.tui.screens.quality_modal import QualityModal

        def on_fmt(fmt: str | None) -> None:
            if fmt is not None:
                from src.tui.screens.watch_modal import WatchModal
                self.app.push_screen(WatchModal(entry, ytdl_format=fmt))

        self.app.push_screen(QualityModal(audio_only=False), on_fmt)

    def action_download(self) -> None:
        entry = self._selected_entry()
        if not entry or entry.get("_is_playlist"):
            return
        from src.tui.screens.download_picker_modal import DownloadPickerModal
        title = entry.get("title", entry.get("id", ""))

        def on_pick(result) -> None:
            if result is None:
                return
            dl_type, fmt = result
            audio_only = (dl_type == "audio")
            from src.tui.screens.download_modal import DownloadModal
            vid = entry.get("id", "")
            self.app.push_screen(DownloadModal(vid, entry, audio_only=audio_only, fmt=fmt))

        self.app.push_screen(DownloadPickerModal(title=title), on_pick)

    def action_copy_url(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        vid = entry.get("id", "")
        if not vid or vid.startswith("__"):
            self.notify("No URL available", severity="warning")
            return
        url = f"https://www.youtube.com/watch?v={vid}"
        for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=url.encode(), check=True, capture_output=True)
                self.notify("URL copied to clipboard")
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        self.notify(f"URL: {url}", timeout=10)

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

    def action_go_back(self) -> None:
        self._cancel_content_proc()
        if self._info_proc and self._info_proc.poll() is None:
            try:
                self._info_proc.terminate()
            except Exception:
                pass
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_up()

    def action_page_next(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.can_go_next():
            panel.load_page(panel.current_page + 1)

    def action_page_prev(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.can_go_prev():
            panel.load_page(panel.current_page - 1)

    def action_page_first(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.current_page != 1:
            panel.load_page(1)

    def action_page_last(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        last = panel.total_pages
        if panel.current_page != last:
            panel.load_page(last)

    # ── Sort picker ───────────────────────────────────────────────────────────

    def action_sort_picker(self) -> None:
        if self._current_tab == "ch-tab-playlists":
            return
        from src.tui.screens.sort_modal import SortModal

        def on_pick(sort: str | None) -> None:
            if sort is None or sort == self._sort:
                return
            self._sort = sort
            self._cancel_content_proc()
            self._start_content_load()

        self.app.push_screen(SortModal(current_sort=self._sort), on_pick)

    # ── Tab picker (tilde) ────────────────────────────────────────────────────

    def action_tab_picker(self) -> None:
        from src.tui.screens.channel_tab_modal import ChannelTabModal

        def on_pick(tab_id: str | None) -> None:
            if not tab_id:
                return
            tabs = self.query_one("#ch-tabs", Tabs)
            tabs.active = tab_id

        self.app.push_screen(ChannelTabModal(self._current_tab), on_pick)

    # ── Reload ────────────────────────────────────────────────────────────────

    def action_reload(self) -> None:
        self._cancel_content_proc()
        self._load_channel_info()
        self._start_content_load()

    # ── Page change from PageIndicator clicks ─────────────────────────────────

    def on_video_list_panel_page_change_requested(
        self, message: VideoListPanel.PageChangeRequested
    ) -> None:
        if message.direction > 0:
            self.action_page_next()
        else:
            self.action_page_prev()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _selected_entry(self) -> dict | None:
        return self.query_one("#ch-video-list", VideoListPanel).selected_entry

    def on_key(self) -> None:
        from textual.widgets import ListView
        focused = self.app.focused
        if focused is None or not isinstance(focused, ListView):
            try:
                self.query_one("#ch-video-list", VideoListPanel)._lv.focus()
            except Exception:
                pass
