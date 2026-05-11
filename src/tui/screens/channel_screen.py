from __future__ import annotations

import re
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static, Tab, Tabs

from src import logger as _logger
from src.tui.widgets.video_list import VideoListPanel
from src.tui.widgets.thumbnail_widget import ThumbnailWidget

_PAGE_SIZE = 20
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_ch_id(info: dict) -> str:
    raw = info.get("channel_id") or info.get("uploader_id") or ""
    if not raw:
        raw = _SAFE_ID_RE.sub("_", info.get("channel_url", "")[:60])
    return "ch_" + raw[:50]


def _fmt_subs(n) -> str:
    if n is None: return ""
    if n >= 1_000_000: return str(round(n * 1e-6, 1)) + "M"
    if n >= 1_000: return str(int(n//1_000)) + "K"
    return str(n)



class ChannelInfoPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield ThumbnailWidget(id="ch-thumbnail")
        yield Static("", id="ch-name", markup=True)
        yield Static("", id="ch-subs", markup=True)
        yield Static("", id="ch-url", markup=True)
        yield Static("", id="ch-sep", markup=False)
        with ScrollableContainer(id="ch-desc-scroll"):
            yield Static("", id="ch-desc", markup=False)
        yield Static("", id="ch-hint", markup=True)

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
        bw_o = "[bold white]"
        bw_c = "[/bold white]"
        dim_o = "[dim]"
        dim_c = "[/dim]"
        self.query_one("#ch-name", Static).update(bw_o + name + bw_c)
        self.query_one("#ch-subs", Static).update(dim_o + subs + dim_c if subs else "")
        self.query_one("#ch-url", Static).update(dim_o + url[:50] + dim_c if url else "")
        self.query_one("#ch-sep", Static).update(chr(9472) * 28)
        self.query_one("#ch-desc", Static).update(desc)

    def update_sort_hint(self, sort: str, tab: str) -> None:
        dim_o = "[dim]"
        dim_c = "[/dim]"
        if tab == "playlists":
            hint = dim_o + "s  sort by date" + dim_c
        else:
            hint = dim_o + "sort: " + sort + "  (s toggle)" + dim_c
        self.query_one("#ch-hint", Static).update(hint)



class ChannelScreen(Screen):
    """Full-screen channel browser: info panel left + video list right."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("backspace", "go_back", "Back", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("left_square_bracket", "page_prev", "Prev", show=False),
        Binding("right_square_bracket", "page_next", "Next", show=False),
        Binding("g", "page_first", show=False),
        Binding("G", "page_last", show=False),
        Binding("s", "toggle_sort", "Sort", show=True),
        Binding("r", "reload", "Reload", show=True),
    ]

    def __init__(self, channel_url: str, channel_name: str = "") -> None:
        super().__init__()
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._current_tab: str = "videos"
        self._sort: str = "date"
        self._info_proc: subprocess.Popen | None = None
        self._content_proc: subprocess.Popen | None = None
        self._active_workers: int = 0
        self._video_panel: VideoListPanel | None = None
        self._thumb_session: int = 0
        self._content_session: int = 0
        self._initial_load_done: bool = False

    def compose(self) -> ComposeResult:
        name = self._channel_name or "Channel"
        with Horizontal(id="ch-main"):
            yield ChannelInfoPanel(id="ch-info-panel")
            with Vertical(id="ch-right"):
                with Tabs(id="ch-tabs"):
                    yield Tab("Videos", id="videos")
                    yield Tab("Playlists", id="playlists")
                yield VideoListPanel(id="ch-video-list")
        yield Footer()

    def on_mount(self) -> None:
        self._video_panel = self.query_one("#ch-video-list", VideoListPanel)
        self.query_one("#ch-info-panel", ChannelInfoPanel).show_loading()
        self._video_panel.clear_and_set_loading()
        self._video_panel.focus()
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
        self._load_content(self._current_tab, self._sort, self._content_session)

    def _worker_start(self) -> None:
        self._active_workers += 1

    def _worker_end(self) -> None:
        self._active_workers = max(0, self._active_workers - 1)

    @work(thread=True, exclusive=True, group="ch_info")
    def _load_channel_info(self) -> None:
        import src.ytdlp as ytdlp
        self._worker_start()
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
        finally:
            self._worker_end()

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
            page_sz = _PAGE_SIZE
            idx2 = 0
            pnum = 1
            while idx2 < len(entries):
                chunk = entries[idx2:idx2 + page_sz]
                self.app.call_from_thread(panel.add_page, pnum, chunk)
                idx2 += page_sz
                pnum += 1
            if session != self._content_session:
                return
            self.app.call_from_thread(panel.load_page, 1)
            self.app.call_from_thread(panel.finish_loading)
        except Exception as exc:
            _logger.debug("channel content error: %s", exc)
            if session == self._content_session:
                self.app.call_from_thread(panel.set_error_message, str(exc))

    def _apply_info(self, info: dict) -> None:
        try:
            panel = self.query_one("#ch-info-panel", ChannelInfoPanel)
            panel.update_info(info)
            panel.update_sort_hint(self._sort, self._current_tab)
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
        """Show the placeholder state on the channel thumbnail (main thread)."""
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

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        if not tab_id:
            return
        prev_tab = self._current_tab
        self._current_tab = tab_id
        try:
            self.query_one("#ch-info-panel", ChannelInfoPanel).update_sort_hint(
                self._sort, self._current_tab
            )
        except Exception:
            pass
        if tab_id == prev_tab and self._initial_load_done:
            return
        self._cancel_content_proc()
        self._start_content_load()

    def _cancel_content_proc(self) -> None:
        if self._content_proc and self._content_proc.poll() is None:
            try: self._content_proc.terminate()
            except Exception: pass
        self._content_proc = None

    def action_go_back(self) -> None:
        self._cancel_content_proc()
        if self._info_proc and self._info_proc.poll() is None:
            try: self._info_proc.terminate()
            except Exception: pass
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_up()

    def action_page_next(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.can_go_next(): panel.load_page(panel.current_page + 1)

    def action_page_prev(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.can_go_prev(): panel.load_page(panel.current_page - 1)

    def action_page_first(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        if panel.current_page != 1: panel.load_page(1)

    def action_page_last(self) -> None:
        panel = self.query_one("#ch-video-list", VideoListPanel)
        last = panel.total_pages
        if panel.current_page != last: panel.load_page(last)

    def action_toggle_sort(self) -> None:
        if self._current_tab == "playlists": return
        self._sort = "views" if self._sort == "date" else "date"
        try:
            panel = self.query_one("#ch-info-panel", ChannelInfoPanel)
            panel.update_sort_hint(self._sort, self._current_tab)
        except Exception: pass
        self._cancel_content_proc()
        self._start_content_load()

    def action_reload(self) -> None:
        self._cancel_content_proc()
        self._load_channel_info()
        self._start_content_load()

    def on_video_list_panel_page_change_requested(
        self, message: VideoListPanel.PageChangeRequested
    ) -> None:
        if message.direction > 0:
            self.action_page_next()
        else:
            self.action_page_prev()

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        pass

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        entry = message.entry
        if not entry:
            return
        from src.tui.screens.video_action_modal import VideoActionModal
        self.app.push_screen(VideoActionModal(entry))

