"""TermTube v2 — search history.

Persists the last N search queries to ~/.config/TermTube/search_history.json.
"""
from __future__ import annotations

import json
import os
import threading

from config import SEARCH_HISTORY_PATH

_lock = threading.Lock()


def _read(max_count: int = 20) -> list[str]:
    try:
        data = json.loads(SEARCH_HISTORY_PATH.read_bytes())
        return data[:max_count] if isinstance(data, list) else []
    except Exception:
        return []


def _write(queries: list[str]) -> None:
    SEARCH_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEARCH_HISTORY_PATH.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(queries, ensure_ascii=False).encode())
    os.replace(tmp, SEARCH_HISTORY_PATH)


def add(query: str, max_count: int = 20) -> None:
    """Add query to the top of history (deduplicating)."""
    q = query.strip()
    if not q:
        return
    with _lock:
        items = _read(max_count)
        items = [i for i in items if i != q]
        items.insert(0, q)
        _write(items[:max_count])


def all_queries(max_count: int = 20) -> list[str]:
    return _read(max_count)


def clear() -> None:
    with _lock:
        _write([])
