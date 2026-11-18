from __future__ import annotations

import re

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Tab, Tabs

from src import channel_bookmarks, channel_ref, innertube, logger
from src.channel_pager import ChannelPager
from src.entries import Entry, PlaylistEntry
from src.errors import classify
from src.tui import keymap
from src.tui.fmt import escape_markup, fmt_breadcrumb
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.channel_playlist import ChannelPlaylistMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.feed_loader import FeedLoaderMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.thumb_loader import load_thumbnail
from src.tui.widgets.channel_info_panel import ChannelInfoPanel
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

_TAB_KINDS = {
    "ch-tab-videos": "videos",
    "ch-tab-shorts": "shorts",
    "ch-tab-live": "live",
    "ch-tab-playlists": "playlists",
}
_TAB_LABELS = {"videos": "Videos", "shorts": "Shorts", "live": "Live", "playlists": "Playlists"}
_DEFAULT_TABS = ("videos", "playlists")
_NO_SORT = {
    "playlists": "Playlists have no sort.",
    "shorts": "Shorts have no sort.",
    "live": "Live streams have no sort.",
}
_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _avatar_id(info: dict) -> str:
    raw = info.get("channel_id") or info.get("uploader_id")
    if not raw:
        raw = _UNSAFE_ID_CHARS.sub("_", info.get("channel_url", "")[:60])
    return "ch_" + raw[:50]


class ChannelScreen(ChannelPlaylistMixin, ListNavMixin, DetailFocusMixin, ItemActionsMixin, AudioBarMixin, Screen):
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
        keymap.FILTER,
        Binding("escape,backspace", "go_back", "Back"),
        *keymap.CHANNEL_PAGE,
        keymap.SEARCH,
        *keymap.GLOBAL,
        Binding("grave_accent", "tab_picker", show=False),
    ]

    def __init__(self, channel_url: str, channel_name: str = "", trail: list[str] | None = None) -> None:
        super().__init__()
        self._trail = list(trail or [])
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._current_tab = "ch-tab-videos"
        self._sort = "date"
        self._content_session = 0
        self._info_avatar_session = 0
        self._content_started = False
        self._pager = ChannelPager()
        self._resolved_id: str | None = None
        self._pending_show = False
        self._shown_tabs: tuple[str, ...] = _DEFAULT_TABS
        self._init_detail_focus()

    def compose(self) -> ComposeResult:
        with Horizontal(id="ch-main"):
            yield ChannelInfoPanel(id="ch-info-panel")
            with Vertical(id="ch-center"):
                yield Tabs(
                    *(Tab(_TAB_LABELS[kind], id=f"ch-tab-{kind}") for kind in _TAB_LABELS),
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
        self._show_tabs(_DEFAULT_TABS)
        self._load_channel_info()
        self.set_timer(0.05, self._start_content_once)
        self._sync_player_bar()

    def _tool_actions(self) -> set[str]:
        tools = {"filter", "bookmark"}
        return tools | {"play_all", "enqueue_all", "save_list"} if self._playlist is not None else tools

    def on_list_view_highlighted(self) -> None:
        self._refresh_actions()

    def _info_panel(self) -> ChannelInfoPanel:
        return self.query_one("#ch-info-panel", ChannelInfoPanel)

    def _hidden_menu_actions(self, entry: Entry) -> set[str]:
        hidden = super()._hidden_menu_actions(entry)
        return hidden if self._is_other_channel(entry) else hidden | {"channel"}

    def _is_other_channel(self, entry: Entry) -> bool:
        """True for a row that names a different channel than this page (a video in a playlist of another channel)."""
        own = self._known_id()
        theirs = entry.get("channel_id") or channel_ref.channel_id(entry.get("channel_url", ""))
        return bool(theirs and own and theirs != own)

    def action_channel(self) -> None:
        entry = self._selected_entry()
        if entry and self._is_other_channel(entry):
            self._open_channel(entry)
        else:
            self._hint("Already on this channel.", "information")

    def _crumbs(self) -> list[str]:
        return [*self._trail, self._display_name()]

    def _display_name(self) -> str:
        info = self._info_panel().info or {}
        return info.get("channel") or self._channel_name or "Channel"

    def _show_breadcrumb(self) -> None:
        parts = [*self._crumbs(), _TAB_LABELS[self._tab_kind()]]
        if self._playlist:
            parts.append(self._playlist.get("_playlist_name") or self._playlist.get("title", "Playlist"))
        self._list().set_breadcrumb(escape_markup(fmt_breadcrumb(parts)) + "  ← esc to go back")

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
        self._show_breadcrumb()
        known = tuple(kind for kind in _TAB_LABELS if kind in info.get("tabs", ()))
        if "videos" in known:
            self._show_tabs(known)
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
        self._pager.reset()
        self._pending_show = False
        self._list().clear_and_set_loading()
        self._show_breadcrumb()
        self._load_content(self._content_kind(), self._sort, self._content_session)

    @work(thread=True, exclusive=True, group="ch_content")
    def _load_content(self, kind: str, sort: str, session: int) -> None:
        call = self.app.call_from_thread
        try:
            page = self._fetch_first_page(kind, sort)
        except Exception as exc:
            logger.debug("channel content: %s", exc)
            page = None
            call(self._show_content_error, session, classify(exc).message)
        if page is not None:
            call(self._show_first_page, session, page)

    def _show_first_page(self, session: int, page: innertube.ChannelPage) -> None:
        if session != self._content_session:
            return
        panel = self._list()
        if not page.entries:
            panel.set_empty_message("No content found.")
            return
        panel.add_entries(1, page.entries)
        panel.load_page(1)
        panel.finish_loading()
        self._pager.start(len(page.entries), page.token)
        self._maybe_prefetch()

    def _show_content_error(self, session: int, message: str) -> None:
        if session == self._content_session:
            self._list().set_error_message(message)

    def _fetch_first_page(self, kind: str, sort: str) -> innertube.ChannelPage:
        if kind == "playlist":
            return self._fetch_playlist_videos()
        if kind == "playlists":
            return innertube.ChannelPage(self._fetch_playlists())
        if kind in ("shorts", "live"):
            return self._fetch_tab(kind)
        return self._fetch_videos(sort)

    def _fetch_tab(self, kind: str) -> innertube.ChannelPage:
        """Shorts or Live: InnerTube only. yt-dlp has no equivalent that is worth the wait."""
        channel_id = self._channel_id()
        page = innertube.fetch_channel_page(channel_id, kind) if channel_id else innertube.ChannelPage([])
        self._label(page.entries)
        return page

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

    def _fetch_videos(self, sort: str) -> innertube.ChannelPage:
        """InnerTube for newest-first (fast, with a continuation); yt-dlp for other sorts or when InnerTube is empty.

        InnerTube's popular and oldest filter chips are not used (decision log 2026-11-18): the other sorts go to
        yt-dlp, which returns one batch with no continuation.
        """
        import src.ytdlp as ytdlp

        channel_id = self._channel_id()
        if channel_id and sort == "date":
            page = innertube.fetch_channel_page(channel_id, "videos")
            if page.entries:
                self._label(page.entries)
                return page
            logger.debug("InnerTube channel videos empty; falling back to yt-dlp")
        return innertube.ChannelPage(
            ytdlp.fetch_channel_videos(self._channel_url, self.app.config, self.app.cache, sort=sort)
        )

    def _label(self, entries: list) -> None:
        """InnerTube channel rows carry no channel name; the page knows it."""
        for entry in entries:
            entry.setdefault("channel", self._channel_name)
            entry.setdefault("uploader", self._channel_name)

    def _maybe_prefetch(self) -> None:
        """Fetch the next page ahead of the user: on the second-to-last held page, never while filtering."""
        panel = self._list()
        if not panel.filter_active and self._pager.wants_more(panel.current_page, panel.total_pages):
            self._extend(show=False)

    def _extend(self, *, show: bool) -> None:
        """Start the next fetch, or when one is in flight make its result show as soon as it lands."""
        panel = self._list()
        if self._pager.fetching:
            if show:
                self._pending_show = True
                panel.show_next_page_loading()
            return
        if not self._pager.token or panel.filter_active:
            return
        token = self._pager.begin_fetch()
        panel.set_progress(self._pager.note())
        if show:
            panel.show_next_page_loading()
        self._extend_content(self._content_kind(), token, show, self._content_session)

    @work(thread=True, exclusive=True, group="ch_extend")
    def _extend_content(self, kind: str, token: str, show: bool, session: int) -> None:
        page = innertube.ChannelPage([])
        try:
            if kind == "playlist":
                page = innertube.fetch_playlist_page(self._playlist["id"], token)
            else:
                page = innertube.fetch_channel_page(self._channel_id() or "", kind, token)
                self._label(page.entries)
        except Exception as exc:
            logger.debug("channel extend: %s", exc)
        self.app.call_from_thread(self._apply_extension, session, page, show)

    def _apply_extension(self, session: int, page: innertube.ChannelPage, show: bool) -> None:
        if session != self._content_session:
            return
        panel = self._list()
        entries = self._pager.finish(page.entries, page.token)
        show = show or self._pending_show
        self._pending_show = False
        panel.set_progress(self._pager.note())
        if entries:
            FeedLoaderMixin._append_pages(panel, entries, show)
        elif show:
            panel.load_page(panel.total_pages, cursor="last")
        self._maybe_prefetch()

    def action_page_next(self) -> None:
        super().action_page_next()
        self._maybe_prefetch()

    def action_goto_end(self) -> None:
        super().action_goto_end()
        self._maybe_prefetch()

    def _on_page_shown(self) -> None:
        """The page-change actions above prefetch themselves."""

    def _on_past_last_page(self) -> None:
        self._extend(show=True)

    def _known_id(self) -> str | None:
        """The id without a lookup: from the URL or the loaded info. Safe on the UI thread."""
        known = channel_ref.channel_id(self._channel_url)
        if known:
            return known
        try:
            info = self._info_panel().info
        except Exception:
            info = None
        if info and channel_ref.is_channel_id(info.get("channel_id", "")):
            return info["channel_id"]
        return self._resolved_id or None

    def _channel_id(self) -> str | None:
        """The ``UC…`` id: from the URL, the loaded channel info, or one lookup (workers only: it blocks)."""
        known = self._known_id()
        if known:
            return known
        if self._resolved_id is None:
            self._resolved_id = innertube.resolve_channel_id(self._channel_url) or ""
        return self._resolved_id or None

    def _show_tabs(self, kinds: tuple[str, ...]) -> None:
        """Show only the tabs the channel has; fall back to Videos if the open tab went away."""
        self._shown_tabs = kinds
        tabs = self.query_one("#ch-tabs", Tabs)
        for kind in _TAB_LABELS:
            if kind in kinds:
                tabs.show(f"ch-tab-{kind}")
            else:
                tabs.hide(f"ch-tab-{kind}")
        if _TAB_KINDS[self._current_tab] not in kinds:
            tabs.active = "ch-tab-videos"

    def _tab_ids(self) -> list[str]:
        return [f"ch-tab-{kind}" for kind in _TAB_LABELS if kind in self._shown_tabs]

    def _tab_kind(self) -> str:
        return _TAB_KINDS[self._current_tab]

    def _content_kind(self) -> str:
        return "playlist" if self._playlist else self._tab_kind()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id if event.tab else None
        if tab_id and (tab_id != self._current_tab or not self._content_started):
            self._playlist = None
            self._current_tab = tab_id
            self._start_content_load()

    def action_tab_prev(self) -> None:
        self._cycle_tab(-1)

    def action_tab_next(self) -> None:
        self._cycle_tab(1)

    def _cycle_tab(self, step: int) -> None:
        order = self._tab_ids()
        target = order[(order.index(self._current_tab) + step) % len(order)]
        self.query_one("#ch-tabs", Tabs).active = target

    def action_tab_picker(self) -> None:
        from src.tui.screens.channel_tab_modal import ChannelTabModal

        def on_pick(tab_id: str | None) -> None:
            if tab_id:
                self.query_one("#ch-tabs", Tabs).active = tab_id

        shown = [(f"ch-tab-{kind}", _TAB_LABELS[kind]) for kind in _TAB_LABELS if kind in self._shown_tabs]
        self.app.push_screen(ChannelTabModal(self._current_tab, shown), on_pick)

    def action_sort(self) -> None:
        if self._tab_kind() != "videos":
            self._hint(_NO_SORT[self._tab_kind()], "information")
            return
        from src.tui.screens.sort_modal import SortModal

        def on_pick(sort: str | None) -> None:
            if sort and sort != self._sort:
                self._sort = sort
                if sort != "date":
                    self.notify("Loading from yt-dlp (slower)…", timeout=3)
                self._start_content_load()

        self.app.push_screen(SortModal(current_sort=self._sort), on_pick)

    def action_bookmark(self) -> None:
        channel_id = self._known_id()
        if not channel_id:
            self._hint("The channel is still loading.", "information")
            return
        info = self._info_panel().info or {}
        name = self._display_name()
        if channel_bookmarks.toggle(channel_id, name, info.get("thumbnail", "")):
            self.notify(f"Following {name} (local, no account needed)", timeout=3)
        else:
            self.notify(f"Unfollowed {name}", timeout=3)

    def action_info(self) -> None:
        if not self._info_panel().toggle_description():
            self._hint("Nothing more to show.", "information")

    def action_reload(self) -> None:
        self._load_channel_info()
        self._start_content_load()

    def action_go_back(self) -> None:
        if not self._close_filter_if_active() and not self._leave_playlist():
            self.app.pop_screen()

    def _on_main_screen(self, method: str) -> None:
        """Pop this page and run ``method`` on the main screen beneath it (search results and quit live there)."""
        self.app.pop_screen()
        getattr(self.app.screen, method)()

    def action_search(self) -> None:
        self._on_main_screen("_open_search_dialog")

    def action_quit_app(self) -> None:
        self._on_main_screen("action_quit_app")

    def action_help(self) -> None:
        from src.tui.screens.help_screen import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_settings(self) -> None:
        from src.tui.screens.settings_modal import SettingsModal

        self.app.push_screen(SettingsModal())
