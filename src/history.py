"""Local watch history (videos played in this TUI), capped at 500 entries."""

from __future__ import annotations
import json
import os
import tempfile
import threading
import time

from src.entries import Entry
from src.plat import get_config_dir

HISTORY_PATH = get_config_dir() / "history.json"

_MAX_ENTRIES = 500
_cache: list[Entry] | None = None

_lock = threading.Lock()


def _load() -> list[Entry]:
    global _cache
    if _cache is not None:
        return _cache
    if not HISTORY_PATH.exists():
        _cache = []
        return _cache
    try:
        _cache = json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        _cache = []
    return _cache


def _save(entries: list[Entry]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=HISTORY_PATH.parent, suffix=".tmp")
    try:
        os.write(fd, data)
        os.close(fd)
        fd = -1
        os.replace(tmp, HISTORY_PATH)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add(entry: Entry) -> None:
    """Record a video as watched (most recent first, deduplicated by id, max 500)."""
    global _cache
    vid = entry.get("id") or entry.get("webpage_url_basename")
    if not vid:
        return
    with _lock:
        entries = [e for e in _load() if e.get("id") != vid]
        entries.insert(0, {**entry, "id": vid, "_watched_at": time.time()})
        _cache = entries[:_MAX_ENTRIES]
        _save(_cache)


def all_entries() -> list[Entry]:
    """Return watch history, most recent first."""
    with _lock:
        return list(_load())
