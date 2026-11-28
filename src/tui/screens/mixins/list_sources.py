from __future__ import annotations

from collections.abc import Callable
from functools import partial

from src.entries import Entry
from src.strings import text
from src.tui.fmt import fmt_day_group
from src.tui.screens.mixins.feed_rows import SEARCH_FETCH_COUNT, pages_for
from src.tui.views import PLAYLIST_VIEW, is_library_view
from src.tui.widgets.video_list import VideoListPanel

_EMPTY_LIBRARY = {
    "library": "feed_loader.empty_library",
    "library:video": "feed_loader.empty_library_video",
    "library:audio": "feed_loader.empty_library_audio",
}


def _day_label(entry: Entry) -> str:
    return fmt_day_group(entry.get("watched_at"))


def _library_matcher(entries: list[Entry], query: str) -> list[Entry]:
    from src import library_query, playlist

    return library_query.rank(entries, query, playlist.membership)


def matcher_for(view: str):
    """The filter for a view: Library views understand `key:value` tokens, other views plain text."""
    return _library_matcher if is_library_view(view) else None


class ListSourcesMixin:
    """The views that are not feeds: subscriptions, following, search, local history, the Library and Local.

    Every method runs on the loader thread and reaches the UI through ``_ui``. Needs ``_ui``, ``_search``,
    ``_history_sort``, ``_detail``, ``_rail_focused``, ``_collection_entries``, ``_set_library_counts``,
    ``_show_empty_feed_modal``, ``_load_local`` and ``app``.
    """

    def _source_loader(self, view: str) -> Callable[[VideoListPanel], None] | None:
        """What fills the list for a non-feed view; None for a view that has no loader."""
        if is_library_view(view):
            return partial(self._load_collection, view)
        loaders = {
            "subscriptions": self._load_subscriptions,
            "following": self._load_following,
            "search": self._load_search,
            "history": self._load_history,
            "local": self._load_local,
        }
        return loaders.get(view)

    def _show_pages(self, panel: VideoListPanel, entries: list[Entry], *, evict: bool = True) -> None:
        call = self._ui
        call(lambda: panel.add_entries(1, entries, evict=evict))
        call(lambda: panel.load_page(1, focus=not self._rail_focused()))
        call(panel.finish_loading)

    def _load_simple_list(self, panel: VideoListPanel, entries: list[Entry], empty: str) -> None:
        if not entries:
            self._ui(panel.set_empty_message, empty)
            return
        self._show_pages(panel, entries, evict=False)

    def _load_history(self, panel: VideoListPanel) -> None:
        from src import history

        recent = self._history_sort == "recent"
        self._ui(lambda: panel.set_view_options(group_by=_day_label if recent else None, show_count=True))
        entries = history.ordered(history.all_entries(), self._history_sort)
        if not entries and not self.app.config.history_enabled:
            self._ui(panel.set_empty_message, text("feed_loader.history_off"))
            return
        self._load_simple_list(panel, entries, text("feed_loader.empty_history"))

    def _load_subscriptions(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        entries = ytdlp.fetch_subscribed_channels(self.app.config, self.app.cache)
        if not entries:
            self._ui(self._show_empty_feed_modal, "subscriptions")
            return
        self._ui(self._detail().set_channel_mode)
        self._show_pages(panel, entries)

    def _load_following(self, panel: VideoListPanel) -> None:
        from src import channel_bookmarks

        entries = channel_bookmarks.entries()
        if not entries:
            self._ui(panel.set_empty_message, text("feed_loader.empty_following"))
            return
        self._ui(self._detail().set_channel_mode)
        self._show_pages(panel, entries, evict=False)

    def _load_search(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        if not self._search.query:
            self._ui(panel.set_empty_message, text("feed_loader.search_prompt"))
            return
        shown: list[Entry] = []
        entries = ytdlp.fetch_search_batch(
            self._search.query, self.app.config, self.app.cache,
            count=SEARCH_FETCH_COUNT, on_first_batch=partial(self._show_first_results, panel, shown),
            sort=self._search.sort, kind=self._search.kind,
        )
        if not shown:
            self._show_pages(panel, entries)
        else:
            shown_ids = {e.get("id") for e in shown}
            rest = [e for e in entries if e.get("id") not in shown_ids]
            if rest:
                self._ui(panel.add_entries, 1 + pages_for(len(shown), panel.page_size), rest)
        if entries:
            self._ui(self._finish_search_load, panel)

    def _show_first_results(self, panel: VideoListPanel, shown: list[Entry], entries: list[Entry]) -> None:
        shown.extend(entries)
        self._ui(panel.add_entries, 1, entries)
        self._ui(panel.load_page, 1)
        self._ui(panel.finish_loading)

    def _finish_search_load(self, panel: VideoListPanel) -> None:
        """Back to the page and row the user left this search on (when they are held), and the back hint."""
        page, focus_id = self._search.take_position()
        if page > 1 or focus_id:
            panel.load_page(page, focus_id=focus_id)
        panel.set_breadcrumb(self._search.breadcrumb())

    def _load_collection(self, view: str, panel: VideoListPanel) -> None:
        """A Library collection or a playlist. Library loads also refresh the rail's counts."""
        if view.startswith(PLAYLIST_VIEW):
            if not (entries := self._collection_entries(view)):
                self._ui(panel.set_empty_message, text("feed_loader.empty_playlist"))
                return
        else:
            from src import library

            config = self.app.config
            self._ui(self._set_library_counts, library.counts(library.all_entries(config.video_dir, config.audio_dir)))
            entries = self._collection_entries(view)
        self._load_simple_list(panel, entries, text(_EMPTY_LIBRARY.get(view, _EMPTY_LIBRARY["library"])))
