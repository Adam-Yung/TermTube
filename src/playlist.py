"""Local playlists (v2): stable ids and slim item snapshots in `playlists.json`, every call under the store lock."""

from __future__ import annotations

import copy
import shutil
import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from src import logger
from src.entries import Entry
from src.history import slim
from src.plat import get_config_dir
from src.store import JsonStore

_PLAYLISTS_PATH = get_config_dir() / "playlists.json"
_V1_BACKUP_SUFFIX = ".v1"
_SNAPSHOT_FIELDS = ("title", "uploader", "channel_id", "duration", "thumbnail", "view_count", "upload_date")


def _migrate(data: Any, from_version: int) -> dict:
    """v1 `{name: [video ids]}` to v2. The old file is copied to `playlists.json.v1` once and never overwritten."""
    backup = _PLAYLISTS_PATH.with_name(_PLAYLISTS_PATH.name + _V1_BACKUP_SUFFIX)
    try:
        if _PLAYLISTS_PATH.exists() and not backup.exists():
            shutil.copy2(_PLAYLISTS_PATH, backup)
    except OSError as exc:
        logger.warning("playlists v1 backup failed: %s", exc)
    playlists: list[dict] = []
    if isinstance(data, dict):
        now = int(time.time())
        for name, ids in data.items():
            if not isinstance(name, str) or not name.strip():
                continue
            ids = ids if isinstance(ids, list) else []
            items = _dedupe([_bare_item(v, now) for v in ids if isinstance(v, str) and v])
            playlists.append(_new_record(_unique_name(playlists, name.strip()), items, now))
    return {"playlists": playlists}


def _bare_item(video_id: str, now: int) -> dict:
    """A migrated v1 item: only the id is known. The title is filled in from the cache when the playlist is opened."""
    return {"id": video_id, "title": "", "uploader": None, "duration": None, "added": now}


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    return [i for i in items if not (i["id"] in seen or seen.add(i["id"]))]


def _new_record(name: str, items: list[dict], now: int) -> dict:
    pid = f"pl_{uuid.uuid4().hex[:8]}"
    return {"id": pid, "name": name, "created": now, "updated": now, "kind": "manual", "items": items}


def _unique_name(playlists: list[dict], name: str, *, skip: str = "") -> str:
    """``name``, or ``name (2)``, ``name (3)``... when another playlist already has it (case-insensitive)."""
    taken = {p["name"].casefold() for p in playlists if p["id"] != skip}
    candidate, n = name, 1
    while candidate.casefold() in taken:
        n += 1
        candidate = f"{name} ({n})"
    return candidate


_store = JsonStore(lambda: _PLAYLISTS_PATH, version=2, default=lambda: {"playlists": []}, migrate=_migrate)


def snapshot(entry: Entry, video_id: str, now: int | None = None) -> dict:
    """The item stored for ``entry``: the row fields (history's slim record) plus when it was added."""
    item = slim(entry, video_id)
    item["title"] = item.get("title") or ""
    item["added"] = int(now if now is not None else time.time())
    return item


def _find(data: dict, pid: str) -> dict | None:
    return next((p for p in data["playlists"] if p["id"] == pid), None)


def _mutate(pid: str, fn: Callable[[dict], Any]) -> Any:
    """Run ``fn(playlist)`` under the lock; a truthy result marks the playlist updated and saves the file."""
    def apply(data: dict) -> Any:
        record = _find(data, pid)
        if record is None:
            return None
        result = fn(record)
        if result:
            record["updated"] = int(time.time())
        return result

    return _store.update(apply)


def list_playlists() -> list[dict]:
    """Copies of all playlists, creation order, items included."""
    return _store.read(lambda data: copy.deepcopy(data["playlists"]))


def get(pid: str) -> dict | None:
    return _store.read(lambda data: copy.deepcopy(_find(data, pid)))


def create(name: str, entries: Iterable[Entry] | None = None) -> dict | None:
    """Create a playlist holding ``entries``. None, changing nothing, if the name is empty or exists (any case)."""
    name = name.strip()

    def apply(data: dict) -> dict | None:
        if not name or _unique_name(data["playlists"], name) != name:
            return None
        now = int(time.time())
        items = _dedupe([snapshot(e, e["id"], now) for e in entries or [] if e.get("id")])
        record = _new_record(name, items, now)
        data["playlists"].append(record)
        return copy.deepcopy(record)

    return _store.update(apply)


def rename(pid: str, name: str) -> bool:
    """False, changing nothing, if the name is empty, taken by another playlist, or the playlist is gone."""
    name = name.strip()

    def apply(data: dict) -> bool:
        record = _find(data, pid)
        if record is None or not name or _unique_name(data["playlists"], name, skip=pid) != name:
            return False
        record["name"], record["updated"] = name, int(time.time())
        return True

    return _store.update(apply)


def delete(pid: str) -> dict | None:
    """Remove the playlist (never any file) and return it, or None if it is gone."""
    def apply(data: dict) -> dict | None:
        record = _find(data, pid)
        if record is not None:
            data["playlists"].remove(record)
        return record

    return _store.update(apply)


def restore(record: dict) -> bool:
    """Put back a playlist returned by `delete` (same id). False if its id or name is taken again."""
    def apply(data: dict) -> bool:
        if _find(data, record["id"]) or _unique_name(data["playlists"], record["name"]) != record["name"]:
            return False
        data["playlists"].append(copy.deepcopy(record))
        return True

    return _store.update(apply)


def add_items(pid: str, entries: Iterable[Entry]) -> int:
    """Append the entries not already in the playlist (a known one is refreshed). Returns how many were added."""
    entries = [e for e in entries if e.get("id")]

    def apply(record: dict) -> int:
        have = {i["id"]: i for i in record["items"]}
        added = 0
        for entry in entries:
            if entry["id"] in have:
                _refresh(have[entry["id"]], entry)
                continue
            item = snapshot(entry, entry["id"])
            record["items"].append(item)
            have[item["id"]] = item
            added += 1
        return added

    return _mutate(pid, apply) or 0


def remove_items(pid: str, video_ids: Iterable[str]) -> list[dict]:
    """Remove those videos. Returns the removed items, each with its old index as `_pos` for `restore_items`."""
    wanted = set(video_ids)

    def apply(record: dict) -> list[dict]:
        removed = [{**item, "_pos": i} for i, item in enumerate(record["items"]) if item["id"] in wanted]
        record["items"] = [i for i in record["items"] if i["id"] not in wanted]
        return removed

    return _mutate(pid, apply) or []


def restore_items(pid: str, items: list[dict]) -> int:
    """Put items from `remove_items` back at their old positions (clamped); ones already present are skipped."""
    def apply(record: dict) -> int:
        have = {i["id"] for i in record["items"]}
        restored = 0
        for item in sorted(items, key=lambda i: i.get("_pos", 0)):
            if item["id"] in have:
                continue
            clean = {k: v for k, v in item.items() if k != "_pos"}
            record["items"].insert(min(item.get("_pos", len(record["items"])), len(record["items"])), clean)
            have.add(item["id"])
            restored += 1
        return restored

    return _mutate(pid, apply) or 0


def move_item(pid: str, video_id: str, to: int) -> bool:
    """Move the video to index ``to``. False, changing nothing, if it is missing or ``to`` is out of range."""
    def apply(record: dict) -> bool:
        items = record["items"]
        at = next((i for i, item in enumerate(items) if item["id"] == video_id), None)
        if at is None or not 0 <= to < len(items) or at == to:
            return False
        items.insert(to, items.pop(at))
        return True

    return bool(_mutate(pid, apply))


def video_playlists(video_id: str) -> list[str]:
    """Names of all playlists containing ``video_id``."""
    def names(data: dict) -> list[str]:
        return [p["name"] for p in data["playlists"] if any(i["id"] == video_id for i in p["items"])]

    return _store.read(names)


def membership() -> dict[str, list[str]]:
    """{video id: names of the playlists holding it}, in one read."""
    def build(data: dict) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for p in data["playlists"]:
            for item in p["items"]:
                out.setdefault(item["id"], []).append(p["name"])
        return out

    return _store.read(build)


def all_video_ids() -> set[str]:
    return _store.read(lambda data: {i["id"] for p in data["playlists"] for i in p["items"]})


def refresh_items(entries: Iterable[Entry]) -> int:
    """Fill in snapshot fields that are empty from richer entries (cache hits, feed rows). Returns items changed."""
    by_id = {e["id"]: e for e in entries if e.get("id")}

    def apply(data: dict) -> int:
        return sum(_refresh(i, by_id[i["id"]]) for p in data["playlists"] for i in p["items"] if i["id"] in by_id)

    return _store.update(apply, defer=True)


def _refresh(item: dict, entry: Entry) -> bool:
    """Copy fields ``item`` lacks from ``entry``. True if anything changed."""
    fresh = slim(entry, item["id"])
    changed = False
    for key in _SNAPSHOT_FIELDS:
        if fresh.get(key) and not item.get(key):
            item[key], changed = fresh[key], True
    return changed


def sync_pins(cache, video_ids: Iterable[str], entries: Iterable[Entry] = ()) -> None:
    """Pin each video that is in some playlist and unpin the rest, so the cache never evicts what a playlist shows."""
    known = {e["id"]: e for e in entries if e.get("id")}
    keep = all_video_ids()
    for vid in set(video_ids):
        if vid in keep:
            cache.pin_video(vid, known.get(vid))
            cache.pin_thumb(vid)
        else:
            cache.unpin_video(vid)
