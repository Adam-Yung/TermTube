from __future__ import annotations

from textual._context import NoActiveAppError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Tab, Tabs

from src import channel_bookmarks, channel_ref
from src.entries import Entry, PlaylistEntry
from src.strings import text
from src.tui import keymap
from src.tui.fmt import escape_markup
from src.tui.screens.channel_tabs import TAB_KINDS, TAB_LABELS
from src.tui.screens.mixins.app_pages import AppPagesMixin
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.channel_content import ChannelContentMixin
from src.tui.screens.mixins.channel_header import ChannelHeaderMixin
from src.tui.screens.mixins.channel_playlist import ChannelPlaylistMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.list_nav import ListNavMixin, lock_tab_bar
from src.tui.widgets.channel_info_panel import ChannelInfoPanel
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

_DEFAULT_TABS = ("videos", "playlists")
_NO_SORT = {
    "playlists": "channel_screen.no_sort_playlists",
    "shorts": "channel_screen.no_sort_shorts",
    "live": "channel_screen.no_sort_live",
}


class ChannelScreen(
    ChannelPlaylistMixin,
    ListNavMixin,
    DetailFocusMixin,
    ItemActionsMixin,
    AudioBarMixin,
    ChannelHeaderMixin,
    ChannelContentMixin,
    AppPagesMixin,
    Screen,
):
    """One channel: info on the left, its videos or playlists in the middle, detail on the right.

    Given ``playlist`` (a playlist row from Search or Home) it is that playlist's page instead: the playlist's header on
    the left, its videos in the middle, no tabs, sort or follow (decision log: ``docs/decisions/playlist-page.md``).

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

    def __init__(
        self,
        channel_url: str,
        channel_name: str = "",
        trail: list[str] | None = None,
        playlist: PlaylistEntry | None = None,
    ) -> None:
        super().__init__()
        self._playlist = playlist
        self._solo = playlist is not None
        self._owner = ("", "")
        self._trail = list(trail or [])
        self._channel_url = channel_url
        self._channel_name = channel_name
        self._current_tab = "ch-tab-videos"
        self._sort = "date"
        self._init_channel_content()
        self._info_avatar_session = 0  # only the newest avatar load may draw
        self._shown_tabs: tuple[str, ...] = _DEFAULT_TABS
        self._init_detail_focus()

    def compose(self) -> ComposeResult:
        with Horizontal(id="ch-main"):
            yield ChannelInfoPanel(id="ch-info-panel")
            with Vertical(id="ch-center"):
                yield Tabs(
                    *(Tab(text(TAB_LABELS[kind]), id=f"ch-tab-{kind}") for kind in TAB_LABELS),
                    id="ch-tabs",
                )
                yield VideoListPanel(id="ch-video-list")
            yield DetailPanel(id="ch-detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._info_panel().show_loading()
        self.set_class(self._solo, "-playlist")
        panel = self._list()
        panel.clear_and_set_loading()
        panel.focus_list()
        lock_tab_bar(self.query_one("#ch-tabs", Tabs))
        if not self._solo:
            self._show_tabs(_DEFAULT_TABS)
            self._load_channel_info()
        self.set_timer(0.05, self._start_content_once)
        self._sync_player_bar()

    def _tool_actions(self) -> set[str]:
        if self._solo:
            return {"filter", "play_all", "enqueue_all", "save_list"}
        tools = {"filter", "bookmark"}
        return tools | {"play_all", "enqueue_all", "save_list"} if self._playlist is not None else tools

    def on_list_view_highlighted(self) -> None:
        self._refresh_actions()

    def _hidden_menu_actions(self, entry: Entry) -> set[str]:
        hidden = super()._hidden_menu_actions(entry)
        return hidden if self._is_other_channel(entry) else hidden | {"channel"}

    def _is_other_channel(self, entry: Entry) -> bool:
        """True for a row that names a different channel than this page (a video in a playlist of another channel)."""
        own = self._known_id()
        theirs = entry.get("channel_id") or channel_ref.channel_id(entry.get("channel_url", ""))
        return bool(theirs and (self._solo or own and theirs != own))

    def action_channel(self) -> None:
        entry = self._selected_entry()
        if entry and self._is_other_channel(entry):
            self._open_channel(entry)
        else:
            self._hint(text("channel_screen.already_here"), "information")

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        self._focus_video(message.entry)

    def _call_ui(self, fn, *args) -> None:
        """Hand a worker's result to the UI thread; dropped when the screen was popped or the app quit meanwhile."""
        try:
            self.app.call_ui(self._run_if_attached, fn, args)
        except NoActiveAppError:  # a popped screen has no app to ask
            return

    def _run_if_attached(self, fn, args: tuple) -> None:
        if self.is_attached:
            fn(*args)

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

    def _show_tabs(self, kinds: tuple[str, ...]) -> None:
        """Show only the tabs the channel has; fall back to Videos if the open tab went away."""
        self._shown_tabs = kinds
        tabs = self.query_one("#ch-tabs", Tabs)
        for kind in TAB_LABELS:
            if kind in kinds:
                tabs.show(f"ch-tab-{kind}")
            else:
                tabs.hide(f"ch-tab-{kind}")
        if TAB_KINDS[self._current_tab] not in kinds:
            tabs.active = "ch-tab-videos"

    def _tab_ids(self) -> list[str]:
        return [f"ch-tab-{kind}" for kind in TAB_LABELS if kind in self._shown_tabs]

    def _tab_kind(self) -> str:
        return TAB_KINDS[self._current_tab]

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if self._solo:
            return
        tab_id = event.tab.id if event.tab else None
        if tab_id and (tab_id != self._current_tab or not self._content_started):
            self._playlist = None
            self._current_tab = tab_id
            self._start_content_load()

    def _no_tabs(self) -> bool:
        """True (with a hint) on a playlist page, which has no tabs, sort or follow."""
        if self._solo:
            self._hint(text("channel_screen.no_tabs_on_playlist"), "information")
        return self._solo

    def action_tab_prev(self) -> None:
        if not self._no_tabs():
            self._cycle_tab(-1)

    def action_tab_next(self) -> None:
        if not self._no_tabs():
            self._cycle_tab(1)

    def _cycle_tab(self, step: int) -> None:
        order = self._tab_ids()
        target = order[(order.index(self._current_tab) + step) % len(order)]
        self.query_one("#ch-tabs", Tabs).active = target

    def action_tab_picker(self) -> None:
        if self._no_tabs():
            return
        from src.tui.screens.channel_tab_modal import ChannelTabModal

        shown = [(f"ch-tab-{kind}", text(TAB_LABELS[kind])) for kind in TAB_LABELS if kind in self._shown_tabs]
        self.app.push_screen(ChannelTabModal(self._current_tab, shown), self._on_tab_picked)

    def _on_tab_picked(self, tab_id: str | None) -> None:
        if tab_id:
            self.query_one("#ch-tabs", Tabs).active = tab_id

    def action_sort(self) -> None:
        if self._no_tabs():
            return
        if self._tab_kind() != "videos":
            self._hint(text(_NO_SORT[self._tab_kind()]), "information")
            return
        from src.tui.screens.sort_modal import SortModal

        self.app.push_screen(SortModal(current_sort=self._sort), self._on_sort_picked)

    def _on_sort_picked(self, sort: str | None) -> None:
        if sort and sort != self._sort:
            self._sort = sort
            if sort != "date":
                self.notify(text("channel_screen.sort_slow"), timeout=3)
            self._start_content_load()

    def action_bookmark(self) -> None:
        if self._no_tabs():
            return
        channel_id = self._known_id()
        if not channel_id:
            self._hint(text("channel_screen.still_loading"), "information")
            return
        info = self._info_panel().info or {}
        name = self._display_name()
        if channel_bookmarks.toggle(channel_id, name, info.get("thumbnail", "")):
            self.notify(text("channel_screen.following", name=escape_markup(name)), timeout=3)
        else:
            self.notify(text("channel_screen.unfollowed", name=escape_markup(name)), timeout=3)

    def action_info(self) -> None:
        if not self._info_panel().toggle_description():
            self._hint(text("channel_screen.nothing_more"), "information")

    def action_owner(self) -> None:
        """Playlist page: open the channel that owns the playlist."""
        name, owner_id = self._owner
        if not self._solo or not owner_id:
            self._hint(text("channel_screen.no_owner"), "information")
            return
        url = f"https://www.youtube.com/channel/{owner_id}"
        self.app.push_screen(ChannelScreen(url, name, trail=self._crumbs_for_owner()))

    def _crumbs_for_owner(self) -> list[str]:
        return [*self._trail, text("channel_screen.playlist_crumb", name=self._display_name())]

    def action_reload(self) -> None:
        if not self._solo:
            self._load_channel_info()
        self._start_content_load()

    def action_go_back(self) -> None:
        if not self._close_filter_if_active() and not self._leave_playlist():
            self.app.pop_screen()

    def _on_main_screen(self, method: str) -> None:
        """Pop this page and run ``method`` on the main screen beneath it (search results live there)."""
        self.app.pop_screen()
        getattr(self.app.screen, method)()

    def action_search(self) -> None:
        self._on_main_screen("_open_search_dialog")
