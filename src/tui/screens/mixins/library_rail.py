from __future__ import annotations

from src import library, playlist
from src.entries import Entry
from src.strings import text
from src.tui.layout import NARROW_BELOW
from src.tui.views import PLAYLIST_VIEW, RAIL_TABS, default_rail_views, playlist_of, tab_of
from src.tui.widgets.library_rail import NEW_PLAYLIST, LibraryRail, RailItem
from src.tui.widgets.video_list import FilterBar

_COLLECTIONS = (
    ("library", "library_rail.all_downloads", ""),
    ("library:video", "library_rail.videos", "video"),
    ("library:audio", "library_rail.audio", "audio"),
)


class LibraryRailMixin:
    """The left rail of the Library, History and Subscriptions tabs: which source the list shows, and rail/list focus.

    The shown source is `_current_tab` (a Library collection or `playlist:<id>`, a History source, `subscriptions` or
    `following`); the tab bar highlights `tab_of(_current_tab)`, and `_rail_views` remembers each tab's source.
    Needs `_list()`, `_hint`, `_load_view` and `_cancel_pending_focus_and_thumb` from the screen, and a
    `#library-rail` child.
    """

    def _init_library_rail(self) -> None:
        self._rail_views = default_rail_views()
        self._library_counts: dict[str, int] = {"": 0, "video": 0, "audio": 0}

    def _rail(self) -> LibraryRail:
        return self.query_one("#library-rail", LibraryRail)

    def _rail_focused(self) -> bool:
        return self.app.focused is self._rail()

    def _rail_playlist(self) -> dict | None:
        """The playlist record under the rail cursor, or None when the cursor is on another entry."""
        item = self._rail().highlighted
        pid = playlist_of(item.view) if item else None
        return playlist.get(pid) if pid is not None else None

    def _rail_view(self) -> str:
        return self._rail_views.get(tab_of(self._current_tab), "")

    def _rail_items(self) -> list[RailItem]:
        """The sources of the current rail tab."""
        builders = {"history": self._history_rail_items, "subscriptions": self._subscription_rail_items}
        return builders.get(tab_of(self._current_tab), self._library_rail_items)()

    def _history_rail_items(self) -> list[RailItem]:
        from src import history

        return [RailItem("history", text("history_rail.local"), len(history.all_entries())),
                RailItem("history:yt", text("history_rail.youtube")),
                RailItem("history:wl", text("history_rail.watch_later"))]

    def _subscription_rail_items(self) -> list[RailItem]:
        return [RailItem("subscriptions", text("subscriptions_rail.subscribed")),
                RailItem("following", text("subscriptions_rail.following"))]

    def _library_rail_items(self) -> list[RailItem]:
        counts = self._library_counts
        items = [RailItem(view, text(label_key), counts[key]) for view, label_key, key in _COLLECTIONS]
        items += [RailItem(f"{PLAYLIST_VIEW}{p['id']}", p["name"], len(p["items"])) for p in playlist.list_playlists()]
        return [*items, RailItem(NEW_PLAYLIST, text("library_rail.new_playlist"))]

    def _refresh_rail(self) -> None:
        self._rail().set_items(self._rail_items(), self._rail_view())

    def _set_library_counts(self, counts: dict[str, int]) -> None:
        self._library_counts = counts
        self._refresh_rail()

    def _show_rail(self, shown: bool) -> None:
        rail = self._rail()
        rail.display = shown
        if shown:
            self._refresh_rail()
            rail.set_narrow(self.size.width < NARROW_BELOW)

    def on_resize(self) -> None:
        for rail in self.query(LibraryRail):
            rail.set_narrow(self.size.width < NARROW_BELOW)

    def _select_collection(self, view: str, *, focus_list: bool = True) -> None:
        """Show ``view`` (a source of a rail tab) in the list, loading it like any tab."""
        self._cancel_pending_focus_and_thumb()
        self._current_tab = self._rail_views[tab_of(view)] = view
        self._refresh_rail()
        self._rail().set_current(view)
        self._load_view(view)
        if view == "following":
            self._list().set_breadcrumb(text("subscriptions_rail.following_crumb"))
        pid = playlist_of(view)
        record = playlist.get(pid) if pid is not None else None
        if record:
            self._list().set_breadcrumb(text("library_rail.playlist_crumb", name=record["name"]))
        if focus_list:
            self._list().focus_list()

    def on_library_rail_chosen(self, message: LibraryRail.Chosen) -> None:
        if message.view == NEW_PLAYLIST:
            self.action_playlist_new()
        else:
            self._select_collection(message.view)

    def action_page_prev(self) -> None:
        """h on the first page of a list with a rail moves to the rail; elsewhere it pages back as usual."""
        if tab_of(self._current_tab) in RAIL_TABS and not self._list().can_go_prev() and self._rail().display:
            self._rail().focus()
        else:
            super().action_page_prev()

    def action_rail_toggle(self) -> None:
        """Tab: move focus between the rail and the list."""
        if tab_of(self._current_tab) not in RAIL_TABS:
            self._hint(text("library_rail.rail_hint"), "information")
        elif self._rail_focused():
            self._list().focus_list()
        elif not isinstance(self.app.focused, FilterBar):
            self._rail().focus()

    def _after_removal(self) -> None:
        """Counts and playlist entries change with a removal; leave a playlist that no longer exists."""
        if tab_of(self._current_tab) != "library":
            return
        self._library_counts = library.counts(library.all_entries(self.app.config.video_dir, self.app.config.audio_dir))
        shown = playlist_of(self._current_tab)
        gone = shown is not None and playlist.get(shown) is None
        if gone:
            self._rail_views = default_rail_views()
        self._refresh_rail()
        if gone:
            self._select_collection("library", focus_list=not self._rail_focused())

    def _collection_entries(self, view: str) -> list[Entry]:
        """Rows of a Library collection or playlist; playlist rows carry their download state."""
        from src.tui.screens.mixins.playlist_tools import item_entries

        pid = playlist_of(view)
        if pid is not None:
            return item_entries(pid, self.app.cache, self.app.config)
        config = self.app.config
        return library.of_kind(library.all_entries(config.video_dir, config.audio_dir), view.partition(":")[2])
