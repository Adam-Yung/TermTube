"""Local watch history — tracks videos watched via this TUI (not Google account)."""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Iterator

HISTORY_PATH = Path.home() / ".local" / "share" / "termtube" / "history.json"


def _load() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


def add(entry: dict) -> None:
    """Record a video as watched. entry should be a video metadata dict."""
    entries = _load()
    vid = entry.get("id") or entry.get("webpage_url_basename")
    if not vid:
        return
    # Remove any existing entry for this video so it moves to top
    entries = [e for e in entries if e.get("id") != vid]
    entries.insert(0, {
        **entry,
        "id": vid,
        "_watched_at": time.time(),
    })
    # Keep last 500 entries
    _save(entries[:500])


def all_entries() -> list[dict]:
    """Return watch history, most recent first."""
    return _load()


def iter_entries() -> Iterator[dict]:
    for e in _load():
        yield e


def clear() -> None:
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()
