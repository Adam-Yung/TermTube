"""The list's filter: the one-line field and the part of ``VideoListPanel`` that shows ranked matches."""

from __future__ import annotations

from collections.abc import Callable

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input

from src import fuzzy
from src.entries import Entry


def paginate(entries: list[Entry], size: int) -> dict[int, list[Entry]]:
    return {n + 1: entries[i:i + size] for n, i in enumerate(range(0, len(entries), size))}


class FilterBar(Input):
    """One-line filter field at the foot of the list. Esc posts ``Cancelled``."""

    DEFAULT_CSS = """
    FilterBar, FilterBar:focus {
        display: none;
        dock: bottom;
        height: 1;
        margin-bottom: 1;
        padding: 0 1;
        border: none;
    }
    """
    BINDINGS = [Binding("escape", "cancel", show=False)]

    class Cancelled(Message):
        pass

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())


class ListFilterMixin:
    """Filtering for ``VideoListPanel``: while ``_filter`` is set the panel shows ``_filtered_pages``.

    Needs ``_filter``, ``_filtered_pages``, ``_anchor_page``, ``_matcher``, ``_pages``, ``_page_size``,
    ``_current_page``, ``_is_loading``, ``_lv``, ``_filter_bar``, ``selected_entry``, ``visited_entries``,
    ``load_page``, ``_page_of``, ``_render_rows`` and ``_update_page_indicator`` from the panel.
    """

    @property
    def filter_active(self) -> bool:
        return bool(self._filter)

    def set_matcher(self, matcher: Callable[[list[Entry], str], list[Entry]] | None) -> None:
        """How the filter ranks entries for the view being loaded; None restores the plain free-text match."""
        self._matcher = matcher or fuzzy.rank

    def open_filter(self) -> bool:
        """Show the filter bar and focus it. False when there is nothing loaded to filter."""
        if self._is_loading or not self._pages:
            return False
        self._filter_bar.display = True
        self._filter_bar.focus()
        return True

    def close_filter(self) -> None:
        """Drop the filter, hide the bar and return focus to the list, the cursor staying on the same video."""
        self._drop_filter()
        self._reset_filter()
        self._lv.focus()

    def _reset_filter(self) -> None:
        self._filter = ""
        self._filtered_pages = {}
        if hasattr(self, "_filter_bar"):
            self._filter_bar.value = ""
            self._filter_bar.display = False

    def _apply_filter(self, query: str) -> None:
        if not query:
            self._drop_filter()
            return
        if not self._filter:
            self._anchor_page = self._current_page
        self._filter = query
        self._rebuild_filtered()
        if self._filtered_pages:
            self.load_page(1, focus=False)
        else:
            self._current_page = 1
            self._render_rows([])
            self._update_page_indicator()

    def _drop_filter(self) -> None:
        if not self._filter:
            return
        selected = self.selected_entry
        sid = selected.get("id") if selected else None
        self._filter = ""
        self._filtered_pages = {}
        page = self._page_of(sid) or min(self._anchor_page, max(self._pages, default=1))
        self.load_page(max(page, 1), focus_id=sid, focus=False)

    def _rebuild_filtered(self) -> None:
        matched = self._matcher(self.visited_entries(), self._filter)
        self._filtered_pages = paginate(matched, self._page_size)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        query = event.value.strip()
        if query != self._filter:
            self._apply_filter(query)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if not self._filter:
            self._filter_bar.display = False
        self._lv.focus()

    def on_filter_bar_cancelled(self, event: FilterBar.Cancelled) -> None:
        event.stop()
        self.close_filter()
