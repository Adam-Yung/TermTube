"""TermTube v2 — watch history + video bookmarks.

Stores the last 500 watched entries in ~/.config/TermTube/history.json.
Bookmarks are stored inline with each entry under the key "_bookmarks".
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator, TypedDict

from config import HISTORY_PATH

_lock = threading.Lock()
_MAX_ENTRIES = 500


class Bookmark(TypedDict):
    position: float   # seconds
    label: str
    created_at: float


def _read() -> list[dict]:
    try:
        return json.loads(HISTORY_PATH.read_bytes())
    except Exception:
        return []


def _write(entries: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_PATH.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(entries, ensure_ascii=False).encode())
    os.replace(tmp, HISTORY_PATH)


# ---------------------------------------------------------------------------
# Watch history
# ---------------------------------------------------------------------------

def add(entry: dict) -> None:
    """Add or promote an entry to the top of watch history."""
    with _lock:
        entries = _read()
        vid = entry.get("id") or entry.get("webpage_url_basename")
        # Preserve bookmarks if already present
        existing = next((e for e in entries if e.get("id") == vid), {})
        bookmarks = existing.get("_bookmarks", [])
        entries = [e for e in entries if e.get("id") != vid]
        new_entry = dict(entry)
        new_entry["_watched_at"] = time.time()
        new_entry["_bookmarks"] = bookmarks
        entries.insert(0, new_entry)
        _write(entries[:_MAX_ENTRIES])


def all_entries() -> list[dict]:
    return _read()


def iter_entries() -> Iterator[dict]:
    yield from _read()


def clear() -> None:
    with _lock:
        _write([])


def is_watched(video_id: str) -> bool:
    return any(e.get("id") == video_id for e in _read())


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------

def add_bookmark(video_id: str, position: float, label: str = "") -> None:
    """Add a bookmark to an entry already in history."""
    with _lock:
        entries = _read()
        for e in entries:
            if e.get("id") == video_id:
                bm: Bookmark = {
                    "position": round(position, 1),
                    "label": label or _format_time(position),
                    "created_at": time.time(),
                }
                e.setdefault("_bookmarks", []).append(bm)
                # Keep sorted, deduplicate positions within 2s
                bms = e["_bookmarks"]
                seen: set[float] = set()
                deduped = []
                for b in sorted(bms, key=lambda x: x["position"]):
                    key = round(b["position"] / 2) * 2
                    if key not in seen:
                        seen.add(key)
                        deduped.append(b)
                e["_bookmarks"] = deduped
                break
        _write(entries)


def get_bookmarks(video_id: str) -> list[Bookmark]:
    for e in _read():
        if e.get("id") == video_id:
            return e.get("_bookmarks", [])
    return []


def remove_bookmark(video_id: str, position: float) -> None:
    with _lock:
        entries = _read()
        for e in entries:
            if e.get("id") == video_id:
                e["_bookmarks"] = [
                    b for b in e.get("_bookmarks", [])
                    if abs(b["position"] - position) > 1.0
                ]
                break
        _write(entries)


def _format_time(secs: float) -> str:
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
