"""Local watch history â tracks videos watched via this TUI (not Google account)."""

from __future__ import annotations
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator

from src.plat import get_config_dir

HISTORY_PATH = get_config_dir() / "history.json"

# Module-level in-memory cache â populated on first load, mutated on add().
# Avoids a full JSON read + write round-trip for every play event.
_cache: list[dict] | None = None

_lock = threading.Lock()


def _load() -> list[dict]:
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


def _save(entries: list[dict]) -> None:
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


def add(entry: dict) -> None:
    """Record a video as watched. entry should be a video metadata dict."""
    with _lock:
        entries = _load()
        vid = entry.get("id") or entry.get("webpage_url_basename")
        if not vid:
            return
        entries = [e for e in entries if e.get("id") != vid]
        entries.insert(0, {
            **entry,
            "id": vid,
            "_watched_at": time.time(),
        })
        trimmed = entries[:500]
        global _cache
        _cache = trimmed
        _save(trimmed)


def all_entries() -> list[dict]:
    """Return watch history, most recent first."""
    with _lock:
        return list(_load())


def iter_entries() -> Iterator[dict]:
    with _lock:
        snapshot = list(_load())
    for e in snapshot:
        yield e


def invalidate_cache() -> None:
    """Force reload from disk on next access (e.g. if modified externally)."""
    with _lock:
        global _cache
        _cache = None
