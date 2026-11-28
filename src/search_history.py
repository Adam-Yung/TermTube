"""Persistent search history: the last 100 queries, newest first, one record per query (compared without case)."""

from __future__ import annotations

import time
from functools import partial

from src.fuzzy import rank_strings
from src.plat import get_config_dir
from src.store import JsonStore

SEARCH_HISTORY_PATH = get_config_dir() / "search_history.json"
MAX_QUERIES = 100

_store = JsonStore(lambda: SEARCH_HISTORY_PATH, version=1, default=list)


def add(query: str, config=None) -> None:
    """Record a search at the top. Nothing is written when `config.search_history_enabled` is false."""
    query = query.strip()
    if not query or (config is not None and not config.search_history_enabled):
        return
    _store.update(partial(_put_first, query=query), defer=True)


def _put_first(data: list, query: str) -> bool:
    key = query.casefold()
    data[:] = [{"q": query, "at": time.time()}] + [r for r in data if r.get("q", "").casefold() != key]
    del data[MAX_QUERIES:]
    return True


def remove(query: str) -> None:
    key = query.casefold()
    _store.update(lambda data: _drop(data, key), defer=True)


def _drop(data: list, key: str) -> bool:
    before = len(data)
    data[:] = [r for r in data if r.get("q", "").casefold() != key]
    return len(data) != before


def clear() -> None:
    """Forget every query and write the empty file at once."""
    _store.update(lambda data: data.clear() or True)


def all_queries() -> list[str]:
    return _store.read(lambda data: [r["q"] for r in data if r.get("q")])


def matching(typed: str) -> list[str]:
    """Queries that match `typed`, best first: prefix before word start before substring, newest first within a tie."""
    return rank_strings(all_queries(), typed)
