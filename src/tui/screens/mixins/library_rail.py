from __future__ import annotations

from src import library, playlist
from src.entries import Entry
from src.tui.widgets.library_rail import NEW_PLAYLIST, LibraryRail, RailItem
from src.tui.widgets.video_list import FilterBar

LIBRARY_VIEWS = ("library", "library:video", "library:audio")
PLAYLIST_VIEW = "playlist:"
ACCOUNT_VIEWS = {"history:yt": "yt_history", "history:wl": "yt_watchlater"}
"""History-tab sources read from the account (read-only), each with its feed key."""
HISTORY_SOURCES = ("history", *ACCOUNT_VIEWS)
NARROW_BELOW = 100
_COLLECTIONS = (
    ("library", "All downloads", ""),
    ("library:video", "Videos", "video"),
    ("library:audio", "Audio", "audio"),
)


def tab_of(view: str) -> str:
    """The tab a view belongs to: Library collections and playlists live on `library`, History sources on `history`."""
    if view in LIBRARY_VIEWS or view.startswith(PLAYLIST_VIEW):
        return "library"
    return "history" if view in HISTORY_SOURCES else view


class LibraryRailMixin:
    """The left rail of the Library tab: which collection the list shows, and focus between rail and list.

    The displayed collection is `_current_tab` (`library`, `library:video`, `library:audio` or `playlist:<id>`); the tab
    bar highlights `tab_of(_current_tab)`. Needs `_list()`, `_hint`, `_load_view` and `_cancel_pending_focus_and_thumb`
    from the screen, and a `#library-rail` child.
    """

    def _init_library_rail(self) -> None:
        self._library_view = "library"
        self._library_counts: dict[str, int] = {"": 0, "video": 0, "audio": 0}

    def _rail(self) -> LibraryRail:
        return self.query_one("#library-rail", LibraryRail)

    def _rail_focused(self) -> bool:
        return self.app.focused is self._rail()

    def _rail_playlist(self) -> dict | None:
        """The playlist record under the rail cursor, or None when the cursor is on another entry."""
        item = self._rail().highlighted
        if item is None or not item.view.startswith(PLAYLIST_VIEW):
            return None
        return playlist.get(item.view.removeprefix(PLAYLIST_VIEW))

    def _rail_items(self) -> list[RailItem]:
        counts = self._library_counts
        items = [RailItem(view, label, counts[key]) for view, label, key in _COLLECTIONS]
        items += [RailItem(f"{PLAYLIST_VIEW}{p['id']}", p["name"], len(p["items"])) for p in playlist.list_playlists()]
        return [*items, RailItem(NEW_PLAYLIST, "+ New playlist")]

    def _refresh_rail(self) -> None:
        self._rail().set_items(self._rail_items(), self._library_view)

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
        """Show ``view`` (a Library collection or `playlist:<id>`) in the list, loading it like any tab."""
        self._cancel_pending_focus_and_thumb()
        self._current_tab = self._library_view = view
        self._refresh_rail()
        self._rail().set_current(view)
        self._load_view(view)
        record = playlist.get(view.removeprefix(PLAYLIST_VIEW)) if view.startswith(PLAYLIST_VIEW) else None
        if record:
            self._list().set_breadcrumb(f"🎵 {record['name']}")
        if focus_list:
            self._list().focus_list()

    def on_library_rail_chosen(self, message: LibraryRail.Chosen) -> None:
        if message.view == NEW_PLAYLIST:
            self.action_playlist_new()
        else:
            self._select_collection(message.view)

    def action_rail_toggle(self) -> None:
        """Tab: move focus between the Library rail and its list."""
        if tab_of(self._current_tab) != "library":
            self._hint("The rail belongs to the Library tab (F5).", "information")
        elif self._rail_focused():
            self._list().focus_list()
        elif not isinstance(self.app.focused, FilterBar):
            self._rail().focus()

    def _after_removal(self) -> None:
        """Counts and playlist entries change with a removal; leave a playlist that no longer exists."""
        if tab_of(self._current_tab) != "library":
            return
        self._library_counts = library.counts(library.all_entries(self.app.config.video_dir, self.app.config.audio_dir))
        shown = self._current_tab.removeprefix(PLAYLIST_VIEW) if self._current_tab.startswith(PLAYLIST_VIEW) else None
        gone = shown is not None and playlist.get(shown) is None
        if gone:
            self._library_view = "library"
        self._refresh_rail()
        if gone:
            self._select_collection("library", focus_list=not self._rail_focused())

    def _collection_entries(self, view: str) -> list[Entry]:
        """Rows of a Library collection or playlist; playlist rows carry their download state."""
        from src.tui.screens.mixins.playlist_tools import item_entries

        if view.startswith(PLAYLIST_VIEW):
            return item_entries(view.removeprefix(PLAYLIST_VIEW), self.app.cache, self.app.config)
        config = self.app.config
        return library.of_kind(library.all_entries(config.video_dir, config.audio_dir), view.partition(":")[2])
