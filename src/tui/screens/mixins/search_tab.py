from __future__ import annotations

from functools import partial

from textual.widgets import Tab, Tabs

from src import logger, search_history
from src.search_stack import SearchStack
from src.strings import text
from src.tui.views import FEED_TABS

_SEARCH_SORTS = [
    ("relevance", text("main_screen.sort_relevance"), "r"),
    ("date", text("main_screen.sort_date"), "d"),
    ("views", text("main_screen.sort_views"), "v"),
]
_SEARCH_TYPES = [
    ("all", text("main_screen.type_all"), "a"),
    ("video", text("main_screen.type_video"), "v"),
    ("channel", text("main_screen.type_channel"), "c"),
    ("playlist", text("main_screen.type_playlist"), "p"),
]
_HISTORY_SORTS = [
    ("recent", text("main_screen.history_recent"), "r"),
    ("plays", text("main_screen.history_plays"), "m"),
    ("time", text("main_screen.history_time"), "l"),
]


class SearchTabMixin:
    """The Search tab (dialog, stack of searches, sort and type) and the ``s`` sort of the local History tab.

    Needs ``_current_tab``, ``_list``, ``_hint``, ``_load_view``, ``_show_rail``, ``_save_feed_stash``,
    ``query_one`` and ``app`` from the screen, which calls ``_init_search_tab`` from ``__init__``.
    """

    def _init_search_tab(self) -> None:
        self._search = SearchStack()
        self._opening_search_tab = False
        self._history_sort = "recent"

    def action_search(self) -> None:
        self._open_search_dialog()

    def _open_search_dialog(self) -> None:
        from src.tui.screens.search_modal import SearchModal

        self.app.push_screen(SearchModal(), self._on_search_query)

    def _on_search_query(self, query: str | None) -> None:
        # On cancel do not touch ``tabs.active``: re-activating the current tab reloads its list.
        if query:
            search_history.add(query, self.app.config)
            self._show_search_results(query)

    def _show_search_results(self, query: str) -> None:
        logger.info("search %r", query)
        if self._current_tab in FEED_TABS:
            self._save_feed_stash(self._current_tab)
        self._save_search_position()
        self._search.push(query)
        self._current_tab = "search"
        self._show_rail(False)
        self._opening_search_tab = True
        self._show_search_frame()

    def _save_search_position(self) -> None:
        """Remember the page and row of the results being left, so coming back lands there."""
        if self._current_tab != "search" or not self._search.query:
            return
        row = self._list().selected_entry
        self._search.save_position(self._list().current_page, row.get("id") if row else None)

    def _show_search_frame(self) -> None:
        """Show the current search on the Search tab (its results come from the cache when they are fresh)."""
        tabs = self.query_one("#nav-tabs", Tabs)
        for tab in tabs.query(Tab):
            if tab.id == "search":
                tab.label = text("main_screen.tab_search_query", query=self._search.query[:20])
        tabs.active = "search"
        self._load_view("search")

    def action_search_sort(self) -> None:
        if self._current_tab == "history":
            self._pick_history_sort()
        else:
            self._pick_search_filter("sort", text("main_screen.sort_results_title"), _SEARCH_SORTS, self._search.sort)

    def _pick_history_sort(self) -> None:
        """s on the local History tab: recent (with day headers), most watched or longest watched."""
        from src.tui.screens.sort_modal import SortModal

        title = text("main_screen.sort_history_title")
        self.app.push_screen(
            SortModal(self._history_sort, options=_HISTORY_SORTS, title=title), self._on_history_sort
        )

    def _on_history_sort(self, value: str | None) -> None:
        if value and value != self._history_sort:
            self._history_sort = value
            self._load_view("history")

    def action_search_type(self) -> None:
        self._pick_search_filter("kind", text("main_screen.result_type_title"), _SEARCH_TYPES, self._search.kind)

    def _pick_search_filter(self, field: str, title: str, options: list[tuple[str, str, str]], current: str) -> None:
        """Ask for a sort or type and reload the current search with it (Search tab only)."""
        if self._current_tab != "search" or not self._search.query:
            self._hint(text("main_screen.search_filter_hint"), "information")
            return
        from src.tui.screens.sort_modal import SortModal

        self.app.push_screen(
            SortModal(current, options=options, title=title), partial(self._on_search_filter, field, current)
        )

    def _on_search_filter(self, field: str, current: str, value: str | None) -> None:
        if value and value != current:
            self._search.set_filter(field, value)
            self._show_search_frame()
