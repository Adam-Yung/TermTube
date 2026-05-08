"""TermTube v2 — explicit hide list.

Stores video IDs the user has explicitly hidden with the `x` key.
Stored in ~/.config/TermTube/hidden.json as a flat list of IDs.
"""
from __future__ import annotations

import json
import os
import threading

from config import HIDDEN_PATH

_lock = threading.Lock()
_cache_set: set[str] | None = None


def _read() -> list[str]:
    try:
        return json.loads(HIDDEN_PATH.read_bytes())
    except Exception:
        return []


def _write(ids: list[str]) -> None:
    global _cache_set
    HIDDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HIDDEN_PATH.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(ids, ensure_ascii=False).encode())
    os.replace(tmp, HIDDEN_PATH)
    _cache_set = set(ids)


def _get_set() -> set[str]:
    global _cache_set
    if _cache_set is None:
        _cache_set = set(_read())
    return _cache_set


def hide(video_id: str) -> None:
    with _lock:
        ids = _read()
        if video_id not in ids:
            ids.append(video_id)
            _write(ids)


def is_hidden(video_id: str) -> bool:
    return video_id in _get_set()


def unhide(video_id: str) -> None:
    with _lock:
        ids = _read()
        _write([i for i in ids if i != video_id])


def all_hidden() -> list[str]:
    return _read()


def clear() -> None:
    with _lock:
        _write([])
