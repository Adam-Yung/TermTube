"""Local watch history (videos played in this TUI): slim records, newest first, capped by `history_max`."""

from __future__ import annotations

import time

from src.entries import Entry
from src.plat import get_config_dir
from src.store import JsonStore

HISTORY_PATH = get_config_dir() / "history.json"

_DEFAULT_MAX = 500
# What a list row and the detail panel show; everything else (description, formats, sidecar paths) is dropped.
_KEPT = ("title", "uploader", "channel_id", "duration", "thumbnail", "view_count", "upload_date")


def _slim(entry: Entry, vid: str) -> dict:
    record = {k: entry.get(k) for k in _KEPT}
    record["uploader"] = entry.get("uploader") or entry.get("channel")
    thumb = record["thumbnail"]
    record["thumbnail"] = thumb if isinstance(thumb, str) else None
    record["id"] = vid
    return record


def _migrate(data: list, from_version: int) -> list:
    out = []
    for old in data:
        vid = old.get("id")
        if not vid:
            continue
        record = _slim(old, vid)
        record.update(watched_at=old.get("_watched_at"), plays=1, seconds=0, resume_s=None, source="local")
        out.append(record)
    return out


_store = JsonStore(lambda: HISTORY_PATH, version=2, default=list, migrate=_migrate)


def add(entry: Entry, config=None) -> None:
    """Record a video as watched: slim record, most recent first, deduplicated by id with `plays` counted.

    Nothing is recorded when `config.history_enabled` is false. The disk write is deferred off the calling thread.
    """
    if config is not None and not config.history_enabled:
        return
    vid = entry.get("id") or entry.get("webpage_url_basename")
    if not vid:
        return
    limit = config.history_max if config is not None else _DEFAULT_MAX
    record = _slim(entry, vid)

    def apply(data: list) -> bool:
        previous = next((e for e in data if e.get("id") == vid), None)
        record.update(
            watched_at=time.time(),
            plays=(previous.get("plays", 1) if previous else 0) + 1,
            seconds=previous.get("seconds", 0) if previous else 0,
            resume_s=previous.get("resume_s") if previous else None,
            source="local",
        )
        data[:] = [record] + [e for e in data if e.get("id") != vid]
        del data[limit:]
        return True

    _store.update(apply, defer=True)


def remove(vid: str) -> bool:
    """Drop one video from the history. Returns False when it was not there."""
    def apply(data: list) -> bool:
        kept = [e for e in data if e.get("id") != vid]
        changed = len(kept) != len(data)
        data[:] = kept
        return changed

    return _store.update(apply, defer=True)


def clear() -> None:
    """Forget the whole history and write the empty file at once."""
    _store.update(lambda data: data.clear() or True)


def all_entries() -> list[Entry]:
    """Return watch history, most recent first (a shallow copy: safe to hold, the dicts are shared)."""
    return _store.read(list)
