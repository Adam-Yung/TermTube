"""Marks and the footer line of ``VideoListPanel``: page indicator, counts, notices and progress."""

from __future__ import annotations

from src.entries import Entry
from src.strings import text


class ListFooterMixin:
    """Multi-row marks and everything the page indicator reports.

    Needs ``_marked``, ``_items_by_id``, ``_pages``, ``_view_pages``, ``_filter``, ``_show_count``, ``_hidden``,
    ``_played_shown``, ``_notice``, ``_progress``, ``_current_page``, ``total_pages``, ``visited_entries`` and
    ``_page_indicator`` from the panel.
    """

    def toggle_mark(self, entry: Entry) -> None:
        vid = entry.get("id", "")
        if not vid:
            return
        self._set_mark(vid, vid not in self._marked)
        self._update_page_indicator()

    def mark_page(self) -> None:
        """Mark every row of the shown page; when all are marked already, unmark them."""
        ids = [e["id"] for e in self._view_pages().get(self._current_page, []) if e.get("id")]
        mark = not all(i in self._marked for i in ids)
        for vid in ids:
            self._set_mark(vid, mark)
        self._update_page_indicator()

    def _set_mark(self, vid: str, marked: bool) -> None:
        if marked:
            self._marked.add(vid)
        else:
            self._marked.discard(vid)
        item = self._items_by_id.get(vid)
        if item is not None:
            item.set_marked(marked)

    def marked_entries(self) -> list[Entry]:
        """Marked rows of the full set (also those on other pages), in list order."""
        return [e for e in self.visited_entries() if e.get("id") in self._marked]

    def _status_note(self) -> str:
        shown = sum(len(p) for p in self._view_pages().values())
        total = sum(len(p) for p in self._pages.values())
        parts = []
        if self._filter:
            parts.append(text("video_list.status_matches", shown=shown, total=total))
        elif self._show_count:
            parts.append(text("video_list.status_total", total=total))
        if self._marked:
            parts.append(text("video_list.status_marked", count=len(self._marked)))
        if self._played_shown:
            parts.append(text("video_list.status_played_shown"))
        elif self._hidden:
            parts.append(text("video_list.status_hidden", count=self._hidden))
        parts += [note for note in (self._notice, self._progress) if note]
        return "  ·  ".join(parts)

    def set_hidden(self, count: int, *, showing: bool = False) -> None:
        """Footer count of rows kept out of the list (Home hides played videos); ``showing`` says they are shown."""
        self._hidden, self._played_shown = count, showing
        self._update_page_indicator()

    def set_notice(self, text: str) -> None:
        """A standing footer note that is not about work in flight (``↑ 4 new · r to refresh``); empty clears it."""
        self._notice = text
        self._update_page_indicator()

    def set_progress(self, text: str) -> None:
        """Extra footer text for work in flight (more pages loading); empty clears it."""
        self._progress = text
        self._update_page_indicator()

    def _update_page_indicator(self) -> None:
        try:
            current = max(self._current_page, 1)
            total = max(self.total_pages, current)
            next_ready = (self._current_page + 1) in self._view_pages()
            self._page_indicator.update_state(
                current=current,
                total=total,
                next_ready=next_ready,
                note=self._status_note(),
            )
        except Exception:
            pass
