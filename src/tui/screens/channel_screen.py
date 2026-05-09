"""TermTube v2 — ChannelScreen.

Drilldown screen for a single YouTube channel.
Pushed when the user clicks a channel name in DetailPanel or presses C.
Uses the same VideoListPanel + DetailPanel layout as MainScreen.

Features:
  - Paged video list with navigation
  - Color-mosaic avatar header
  - Subscribe/unsubscribe (local subscriptions list)
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

import ytdlp as _ytdlp
import logger
from config import Config, CONFIG_DIR
from tui.components.app_header import AppHeader
from tui.panels.detail_panel import DetailPanel
from tui.panels.video_list_panel import VideoListPanel

_SUBSCRIPTIONS_PATH = CONFIG_DIR / "subscriptions.json"


def _load_subscriptions() -> list[dict]:
    try:
        return json.loads(_SUBSCRIPTIONS_PATH.read_bytes())
    except Exception:
        return []


def _save_subscriptions(subs: list[dict]) -> None:
    _SUBSCRIPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _SUBSCRIPTIONS_PATH.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(subs, ensure_ascii=False).encode())
    os.replace(tmp, _SUBSCRIPTIONS_PATH)


def is_subscribed(channel_url: str) -> bool:
    return any(s.get("url") == channel_url for s in _load_subscriptions())


def subscribe(channel_url: str, channel_name: str) -> None:
    subs = _load_subscriptions()
    if not any(s.get("url") == channel_url for s in subs):
        subs.append({"url": channel_url, "name": channel_name})
        _save_subscriptions(subs)


def unsubscribe(channel_url: str) -> None:
    subs = _load_subscriptions()
    _save_subscriptions([s for s in subs if s.get("url") != channel_url])


class ChannelScreen(Screen):
    """Shows videos for a specific channel."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("J", "next_page", "Next page", show=False),
        Binding("K", "prev_page", "Prev page", show=False),
        Binding("enter", "select_entry", "Select", show=False),
        Binding("f", "toggle_subscribe", "Subscribe/Unsubscribe"),
    ]

    DEFAULT_CSS = """
    ChannelScreen {
        layout: vertical;
    }
    #channel-header-bar {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
        dock: top;
    }
    #channel-avatar {
        height: 2;
        width: 16;
        dock: left;
    }
    #channel-name {
        color: $accent;
        text-style: bold;
        height: 1;
    }
    #channel-sub-btn {
        dock: right;
        width: auto;
        min-width: 14;
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
        self._subscribed = is_subscribed(channel_url)

    def compose(self) -> ComposeResult:
        yield AppHeader(theme=self._config.get("theme", "crimson"), id="ch-app-header")
        with Static(id="channel-header-bar"):
            yield Static("", id="channel-avatar")
            yield Static(f" {self._channel_name}", id="channel-name")
            sub_label = "★ Subscribed" if self._subscribed else "☆ Subscribe"
            sub_variant = "success" if self._subscribed else "default"
            yield Button(sub_label, variant=sub_variant, id="channel-sub-btn")
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
        self._render_avatar_placeholder()
        self._fetch_page(1)

    def _render_avatar_placeholder(self) -> None:
        """Render a small color-mosaic as channel avatar placeholder."""
        colors = [(80, 20, 20), (200, 60, 60), (255, 100, 100), (200, 60, 60)]
        text = Text(no_wrap=True, overflow="fold")
        for row in range(2):
            for col in range(8):
                t = col / 7
                idx = t * (len(colors) - 1)
                lo, hi = int(idx), min(int(idx) + 1, len(colors) - 1)
                frac = idx - lo
                fg = tuple(int(colors[lo][ch] * (1 - frac) + colors[hi][ch] * frac) for ch in range(3))
                style = Style(bgcolor=Color.from_rgb(*fg))
                text.append(" ", style)
            if row < 1:
                text.append("\n")
        try:
            self.query_one("#channel-avatar", Static).update(text)
        except Exception:
            pass

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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "channel-sub-btn":
            self.action_toggle_subscribe()

    def action_toggle_subscribe(self) -> None:
        if self._subscribed:
            unsubscribe(self._channel_url)
            self._subscribed = False
        else:
            subscribe(self._channel_url, self._channel_name)
            self._subscribed = True
        self._update_sub_button()

    def _update_sub_button(self) -> None:
        try:
            btn = self.query_one("#channel-sub-btn", Button)
            if self._subscribed:
                btn.label = "★ Subscribed"
                btn.variant = "success"
            else:
                btn.label = "☆ Subscribe"
                btn.variant = "default"
        except Exception:
            pass

    def action_next_page(self) -> None:
        if self._page < self._total_pages:
            self._fetch_page(self._page + 1)

    def action_prev_page(self) -> None:
        if self._page > 1:
            self._fetch_page(self._page - 1)

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
