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


def slim(entry: Entry, vid: str, keys: tuple[str, ...] = _KEPT) -> dict:
    """The fields of ``entry`` listed in ``keys`` (list row and detail panel by default), keyed by ``vid``."""
    record = {k: entry.get(k) for k in keys}
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
        record = slim(old, vid)
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
    record = slim(entry, vid)

    def apply(data: list) -> bool:
        previous = next((e for e in data if e.get("id") == vid), None)
        if previous and not record["duration"]:
            record["duration"] = previous.get("duration")
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


def get(vid: str) -> Entry | None:
    """A copy of the history record for ``vid``, or None."""
    return _store.read(lambda data: next((dict(e) for e in data if e.get("id") == vid), None))


def record_progress(vid: str, *, resume_s: int | None, watched: float, duration: float | None = None) -> None:
    """Add ``watched`` seconds to a recorded video and set where to resume (None: play from the start next time).

    A video with no record (history off, or removed meanwhile) is left alone. The disk write is deferred.
    """
    def apply(data: list) -> bool:
        record = next((e for e in data if e.get("id") == vid), None)
        if record is None:
            return False
        record["resume_s"] = resume_s
        record["seconds"] = round((record.get("seconds") or 0) + watched, 1)
        if duration and not record.get("duration"):
            record["duration"] = int(duration)
        return True

    _store.update(apply, defer=True)


def flush() -> None:
    """Write deferred changes now (the quit path does not wait for the background timer)."""
    _store.flush()


def ordered(entries: list[Entry], sort: str) -> list[Entry]:
    """``entries`` (newest first) as ``sort``: ``plays`` (then time watched) or ``time``; else unchanged. Stable."""
    if sort == "plays":
        return sorted(entries, key=lambda e: (e.get("plays") or 0, e.get("seconds") or 0), reverse=True)
    if sort == "time":
        return sorted(entries, key=lambda e: e.get("seconds") or 0, reverse=True)
    return entries


def remove_many(ids: list[str]) -> list[Entry]:
    """Drop videos from the history. Returns copies of the records removed (for undo)."""
    wanted = set(ids)
    removed: list[Entry] = []

    def apply(data: list) -> bool:
        removed.extend(dict(e) for e in data if e.get("id") in wanted)
        data[:] = [e for e in data if e.get("id") not in wanted]
        return bool(removed)

    _store.update(apply, defer=True)
    return removed


def restore(records: list[Entry]) -> None:
    """Put removed records back in `watched_at` order. A video watched again since stays as its newer record."""
    def apply(data: list) -> bool:
        present = {e.get("id") for e in data}
        back = [dict(r) for r in records if r.get("id") not in present]
        data.extend(back)
        data.sort(key=lambda e: e.get("watched_at") or 0, reverse=True)
        return bool(back)

    _store.update(apply, defer=True)


def import_entries(entries: list[Entry], config=None) -> int:
    """Copy YouTube history rows into the local history. Returns how many were added.

    Rows already present (by id) win and stay untouched. Imported rows carry `source="yt"` and `watched_at=None`
    ("unknown time": YouTube's history gives no timestamps): they go after every dated row, under the "Earlier"
    day header, and are the first to fall off the `history_max` cap.
    """
    limit = config.history_max if config is not None else _DEFAULT_MAX
    added = 0

    def apply(data: list) -> bool:
        nonlocal added
        present = {e.get("id") for e in data}
        for entry in entries:
            vid = entry.get("id")
            if not vid or vid in present:
                continue
            present.add(vid)
            record = slim(entry, vid)
            record.update(watched_at=None, plays=0, seconds=0, resume_s=None, source="yt")
            data.append(record)
            added += 1
        del data[limit:]
        return bool(added)

    _store.update(apply)
    return added


def clear() -> None:
    """Forget the whole history and write the empty file at once."""
    _store.update(lambda data: data.clear() or True)


def all_entries() -> list[Entry]:
    """Return watch history, most recent first (a shallow copy: safe to hold, the dicts are shared)."""
    return _store.read(list)
