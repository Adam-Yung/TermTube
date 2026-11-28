"""Numbers and row rules the feed loader, its paging and the list sources share."""

from __future__ import annotations

from src.entries import Entry

BATCH_FETCH_COUNT = 80
FIRST_BATCH_COUNT = 15
SEARCH_FETCH_COUNT = 50


def tag_yt(entries: list[Entry]) -> list[Entry]:
    """Copies of account rows marked `_yt` (they show the YT badge); the cached originals stay untouched."""
    return [{**e, "_yt": True} for e in entries]


def pages_for(count: int, page_size: int) -> int:
    return -(-count // page_size)
