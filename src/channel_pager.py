"""Paging state of one channel tab: the continuation token, the entry cap and the footer note. No Textual."""

from __future__ import annotations

from src.entries import Entry

MAX_ENTRIES = 200


class ChannelPager:
    """What a channel tab still has to fetch. The screen drives it from the UI thread only."""

    def __init__(self, cap: int = MAX_ENTRIES) -> None:
        self.cap = cap
        self.token = ""
        self.loaded = 0
        self.fetching = False
        self._batch = 0
        self.total: int | None = None  # the playlist's own count, when its header said

    def reset(self) -> None:
        self.token = ""
        self.loaded = 0
        self.fetching = False
        self._batch = 0
        self.total = None

    def start(self, count: int, token: str, total: int | None = None) -> None:
        """The first page arrived with ``count`` entries; ``total`` is the list's own length when it is known."""
        self.total = total
        self.loaded = count
        self._batch = count
        self.token = token if count < self.cap else ""

    def wants_more(self, current_page: int, total_pages: int) -> bool:
        """True when the user is on the second-to-last (or last) held page and a next page exists."""
        return bool(self.token) and not self.fetching and current_page >= total_pages - 1

    def begin_fetch(self) -> str:
        self.fetching = True
        return self.token

    def finish(self, entries: list[Entry], token: str) -> list[Entry]:
        """A fetched page arrived: the entries that fit under the cap. Failure is an empty page with no token."""
        self.fetching = False
        entries = entries[: max(0, self.cap - self.loaded)]
        self.loaded += len(entries)
        self._batch = len(entries) or self._batch
        self.token = token if self.loaded < self.cap else ""
        return entries

    def note(self) -> str:
        """Footer text next to the page indicator."""
        if self.fetching:
            return f"loading {self._batch} more…"
        if self.loaded >= self.cap:
            if self.total and self.total > self.cap:
                return f"first {self.cap} of {self.total:,} shown"
            return f"first {self.cap} shown"
        return ""
