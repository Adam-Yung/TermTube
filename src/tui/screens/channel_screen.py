"""TermTube v2 — ChannelScreen.

Drilldown screen for a single YouTube channel.
Pushed when the user clicks a channel name in DetailPanel or presses C.
Uses the same VideoListPanel + DetailPanel layout as MainScreen.
"""
from __future__ import annotations

import threading

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

import ytdlp as _ytdlp
import logger
from config import Config
from tui.components.app_header import AppHeader
from tui.panels.detail_panel import DetailPanel
from tui.panels.video_list_panel import VideoListPanel


class ChannelScreen(Screen):
    """Shows videos for a specific channel."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select_entry", "Select", show=False),
    ]

    DEFAULT_CSS = """
    ChannelScreen {
        layout: vertical;
    }
    #channel-header-bar {
        height: 1;
        background: $surface-darken-1;
        color: $accent;
        text-style: bold;
        padding: 0 1;
        dock: top;
    }
    #channel-columns {
        height: 1fr;
        layout: horizontal;
    }
    """

    def __init__(self, channel_url: str, channel_name: str, config: Config, **kwargs) -> None:
        super().__init__(**kwargs)
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._config = config
        self._page = 1
        self._total_pages = 1
        self._cancel = threading.Event()

    def compose(self) -> ComposeResult:
        yield AppHeader(theme=self._config.get("theme", "crimson"), id="ch-app-header")
        yield Static(f" ⊞  {self._channel_name}", id="channel-header-bar")
        with Horizontal(id="channel-columns"):
            yield VideoListPanel(
                theme=self._config.get("theme", "crimson"),
                id="ch-video-list",
            )
            yield DetailPanel(
                theme=self._config.get("theme", "crimson"),
                id="ch-detail-panel",
            )
        yield Footer()

    def on_mount(self) -> None:
        vl = self.query_one("#ch-video-list", VideoListPanel)
        vl.set_dirs(self._config.video_dir, self._config.audio_dir)
        vl.set_header(f" {self._channel_name}")
        self._fetch_page(1)

    @work(thread=True, exclusive=True, group="ch-feed")
    def _fetch_page(self, page: int) -> None:
        self.app.call_from_thread(
            self.query_one("#ch-video-list", VideoListPanel).set_loading, True
        )
        self.app.call_from_thread(
            self.query_one("#ch-app-header", AppHeader).set_loading, True
        )
        try:
            entries, has_more = _ytdlp.fetch_page(
                self._channel_url, page, self._config, cancel_event=self._cancel
            )
        except Exception as exc:
            logger.warning("channel fetch error: %s", exc)
            entries, has_more = [], False

        if self._cancel.is_set():
            return

        total = self._total_pages
        if has_more and page >= total:
            total = page + 1
        elif not has_more:
            total = page
        self._total_pages = total
        self._page = page

        self.app.call_from_thread(
            self.query_one("#ch-video-list", VideoListPanel).load_entries,
            entries,
            feed_key=self._channel_url,
            page=page,
            total_pages=total,
            loading=False,
        )
        self.app.call_from_thread(
            self.query_one("#ch-app-header", AppHeader).set_loading, False
        )
        if entries:
            self.app.call_from_thread(self._focus_entry, entries[0])

    def _focus_entry(self, entry: dict) -> None:
        dp = self.query_one("#ch-detail-panel", DetailPanel)
        dp.update_basic(entry)
        dp.set_thumbnail_loading()

    def on_video_list_panel_selected(self, event: VideoListPanel.Selected) -> None:
        dp = self.query_one("#ch-detail-panel", DetailPanel)
        dp.update_basic(event.entry)

    def on_video_list_panel_page_change_requested(
        self, event: VideoListPanel.PageChangeRequested
    ) -> None:
        page = self._page + event.direction
        if 1 <= page <= self._total_pages:
            self._fetch_page(page)

    def action_cursor_top(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_to_top()

    def action_cursor_bottom(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_to_bottom()

    def action_cursor_down(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#ch-video-list", VideoListPanel).cursor_up()

    def action_pop_screen(self) -> None:
        self._cancel.set()
        self.app.pop_screen()
