from __future__ import annotations

import re

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Tab, Tabs

from src import feeds, innertube, logger
from src.entries import Entry, PlaylistEntry, VideoEntry
from src.tui import keymap
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.thumb_loader import load_thumbnail
from src.tui.widgets.channel_info_panel import ChannelInfoPanel
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

_TAB_ORDER = ("ch-tab-videos", "ch-tab-playlists")
_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _avatar_id(info: dict) -> str:
    raw = info.get("channel_id") or info.get("uploader_id")
    if not raw:
        raw = _UNSAFE_ID_CHARS.sub("_", info.get("channel_url", "")[:60])
    return "ch_" + raw[:50]


class ChannelScreen(ListNavMixin, DetailFocusMixin, ItemActionsMixin, AudioBarMixin, Screen):
    """One channel: info on the left, its videos or playlists in the middle, detail on the right.

    Audio belongs to ``app.audio``; this screen forwards the keys and mirrors playback state
    into its own action bar.
    """

    _LIST_ID = "#ch-video-list"
    _DETAIL_ID = "#ch-detail-panel"

    BINDINGS = [
        *keymap.LIST_NAV,
        *keymap.PLAYBACK,
        *keymap.ITEM_ACTIONS,
        Binding("escape,backspace", "go_back", "Back"),
        Binding("s", "sort", "Sort"),
        Binding("r", "reload", "Reload"),
        Binding("grave_accent", "tab_picker", show=False),
    ]

    def __init__(self, channel_url: str, channel_name: str = "") -> None:
        super().__init__()
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._current_tab = "ch-tab-videos"
        self._sort = "date"
        self._content_session = 0
        self._info_avatar_session = 0
        self._content_started = False
        self._init_detail_focus()

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
        self._info_panel().show_loading()
        panel = self._list()
        panel.clear_and_set_loading()
        panel.focus_list()
        tabs = self.query_one("#ch-tabs", Tabs)
        tabs.can_focus = False
        for tab in tabs.query(Tab):
            tab.can_focus = False
        self._load_channel_info()
        self.set_timer(0.05, self._start_content_once)
        self._sync_player_bar()

    def _info_panel(self) -> ChannelInfoPanel:
        return self.query_one("#ch-info-panel", ChannelInfoPanel)

    def _hidden_menu_actions(self, entry: Entry) -> set[str]:
        return super()._hidden_menu_actions(entry) | {"channel"}

    def action_channel(self) -> None:
        self._hint("Already on this channel.", "information")

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        self._focus_video(message.entry)

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()

    @work(thread=True, exclusive=True, group="ch_info")
    def _load_channel_info(self) -> None:
        import src.ytdlp as ytdlp

        try:
            info = ytdlp.fetch_channel_info(self._channel_url, self.app.config, self.app.cache)
        except Exception as exc:
            logger.debug("channel info: %s", exc)
            info = None
        if info:
            self.app.call_from_thread(self._apply_info, info)
        else:
            self.app.call_from_thread(self._show_info_error)

    def _show_info_error(self) -> None:
        self._info_panel().show_error()

    def _apply_info(self, info: dict) -> None:
        panel = self._info_panel()
        panel.update_info(info)
        url = info.get("thumbnail", "")
        if not url:
            panel.set_thumbnail_placeholder()
            return
        avatar_id = _avatar_id(info)
        panel.set_avatar_id(avatar_id)
        panel.set_thumbnail_loading()
        self._info_avatar_session += 1
        self._avatar_worker(avatar_id, url, self._info_avatar_session)

    @work(thread=True, exclusive=True, group="ch_thumb")
    def _avatar_worker(self, avatar_id: str, url: str, session: int) -> None:
        load_thumbnail(
            self.app, self._info_panel(), avatar_id, url=url,
            is_current=lambda: session == self._info_avatar_session,
        )

    def _start_content_once(self) -> None:
        if not self._content_started:
            self._start_content_load()

    def _start_content_load(self) -> None:
        self._content_started = True
        self._content_session += 1
        self._list().clear_and_set_loading()
        kind = "playlists" if self._current_tab == "ch-tab-playlists" else "videos"
        self._load_content(kind, self._sort, self._content_session)

    @work(thread=True, exclusive=True, group="ch_content")
    def _load_content(self, kind: str, sort: str, session: int) -> None:

        panel = self._list()
        call = self.app.call_from_thread
        try:
            if kind == "playlists":
                entries = self._fetch_playlists()
            else:
                entries = self._fetch_videos(sort)
            if session != self._content_session:
                return
            if not entries:
                call(panel.set_empty_message, "No content found.")
                return
            call(panel.add_entries, 1, entries)
            call(panel.load_page, 1)
            call(panel.finish_loading)
        except Exception as exc:
            logger.debug("channel content: %s", exc)
            if session == self._content_session:
                call(panel.set_error_message, str(exc))

    def _fetch_playlists(self) -> list[PlaylistEntry]:
        """InnerTube browse (fast); yt-dlp when the id is unknown or the response is empty."""
        import src.ytdlp as ytdlp

        channel_id = self._channel_id()
        if channel_id:
            entries = innertube.fetch_channel_playlists(channel_id)
            if entries:
                return entries
            logger.debug("InnerTube channel playlists empty; falling back to yt-dlp")
        return ytdlp.fetch_channel_playlists(self._channel_url, self.app.config, self.app.cache)

    def _fetch_videos(self, sort: str) -> list[VideoEntry]:
        """RSS or InnerTube for newest-first (fast); yt-dlp for other sorts or when both fail."""
        import src.ytdlp as ytdlp

        channel_id = self._channel_id()
        if channel_id and sort == "date":
            entries = feeds.channel_latest(channel_id)
            if entries:
                for entry in entries:
                    entry.setdefault("channel", self._channel_name)
                    entry.setdefault("uploader", self._channel_name)
                return entries
            logger.debug("RSS and InnerTube channel feed empty; falling back to yt-dlp")
        return ytdlp.fetch_channel_videos(self._channel_url, self.app.config, self.app.cache, sort=sort)

    def _channel_id(self) -> str | None:
        """The ``UC…`` id, from the URL or from the loaded channel info."""
        if "/channel/UC" in self._channel_url:
            return self._channel_url.split("/channel/")[1].split("/")[0].split("?")[0]
        try:
            info = self._info_panel().info
        except Exception:
            return None
        if info and info.get("channel_id", "").startswith("UC"):
            return info["channel_id"]
        return None

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        if tab_id and (tab_id != self._current_tab or not self._content_started):
            self._current_tab = tab_id
            self._start_content_load()

    def action_tab_prev(self) -> None:
        self._cycle_tab(-1)

    def action_tab_next(self) -> None:
        self._cycle_tab(1)

    def _cycle_tab(self, step: int) -> None:
        target = _TAB_ORDER[(_TAB_ORDER.index(self._current_tab) + step) % len(_TAB_ORDER)]
        self.query_one("#ch-tabs", Tabs).active = target

    def action_tab_picker(self) -> None:
        from src.tui.screens.channel_tab_modal import ChannelTabModal

        def on_pick(tab_id: str | None) -> None:
            if tab_id:
                self.query_one("#ch-tabs", Tabs).active = tab_id

        self.app.push_screen(ChannelTabModal(self._current_tab), on_pick)

    def action_sort(self) -> None:
        if self._current_tab == "ch-tab-playlists":
            self._hint("Playlists have no sort.", "information")
            return
        from src.tui.screens.sort_modal import SortModal

        def on_pick(sort: str | None) -> None:
            if sort and sort != self._sort:
                self._sort = sort
                if sort != "date":
                    self.notify("Loading from yt-dlp (slower)…", timeout=3)
                self._start_content_load()

        self.app.push_screen(SortModal(current_sort=self._sort), on_pick)

    def action_reload(self) -> None:
        self._load_channel_info()
        self._start_content_load()

    def action_go_back(self) -> None:
        self.app.pop_screen()
