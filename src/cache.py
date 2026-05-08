"""TermTube v2 — disk + RAM cache.

Layout under ~/.cache/termtube/:
  videos/{id}.json          full metadata per video (TTL-managed)
  feed_{key}_p{n}.json      paged feed index (list of entry dicts)
  feed_{key}_stash.json     page-1 stash from last session (instant load)
  thumbs/{id}.jpg           JPEG thumbnails
  sb/{id}.json              SponsorBlock segments per video
  quality/{id}_{mode}.txt   last quality choice per (video, mode)

Design rules:
  - All writes are atomic (tmp + os.replace).
  - No suppression subsystem — removed in v2.
  - Paged keys allow backward navigation with zero re-fetch.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path("~/.cache/termtube").expanduser()

_write_lock = threading.Lock()

# Fields stripped from full metadata when caching (saves ~60% disk per entry)
_FAT_FIELDS = frozenset(
    ["formats", "requested_formats", "subtitles", "automatic_captions",
     "captions", "heatmap", "fragments", "downloader_options"]
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_bytes())
    except Exception:
        return None


def _write_json(path: Path, obj: Any) -> None:
    with _write_lock:
        _atomic_write(path, json.dumps(obj, ensure_ascii=False).encode())


# ---------------------------------------------------------------------------
# Video metadata cache
# ---------------------------------------------------------------------------

def _video_path(video_id: str) -> Path:
    return CACHE_DIR / "videos" / f"{video_id}.json"


def get_video(video_id: str, ttl: int = 86400) -> dict | None:
    path = _video_path(video_id)
    data = _read_json(path)
    if data is None:
        return None
    age = time.time() - data.get("_cached_at", 0)
    if age > ttl:
        return None
    return data


def get_video_raw(video_id: str) -> dict | None:
    """Return cached metadata ignoring TTL (stale-while-revalidate use)."""
    return _read_json(_video_path(video_id))


def put_video(entry: dict) -> None:
    slim = {k: v for k, v in entry.items() if k not in _FAT_FIELDS}
    slim["_cached_at"] = time.time()
    _write_json(_video_path(slim.get("id", slim.get("webpage_url_basename", "unknown"))), slim)


# ---------------------------------------------------------------------------
# Paged feed cache
# ---------------------------------------------------------------------------

def _page_path(feed_key: str, page: int) -> Path:
    return CACHE_DIR / f"feed_{feed_key}_p{page}.json"


def _stash_path(feed_key: str) -> Path:
    return CACHE_DIR / f"feed_{feed_key}_stash.json"


def has_page(feed_key: str, page: int, ttl: int = 3600) -> bool:
    path = _page_path(feed_key, page)
    data = _read_json(path)
    if not data:
        return False
    age = time.time() - data.get("_cached_at", 0)
    return age <= ttl


def get_page(feed_key: str, page: int, ttl: int = 3600) -> list[dict] | None:
    path = _page_path(feed_key, page)
    data = _read_json(path)
    if not data:
        return None
    age = time.time() - data.get("_cached_at", 0)
    if age > ttl:
        return None
    return data.get("entries", [])


def get_page_stale(feed_key: str, page: int) -> list[dict] | None:
    """Return cached page ignoring TTL."""
    data = _read_json(_page_path(feed_key, page))
    return data.get("entries", []) if data else None


def put_page(feed_key: str, page: int, entries: list[dict]) -> None:
    _write_json(_page_path(feed_key, page), {"_cached_at": time.time(), "entries": entries})


def page_age(feed_key: str, page: int) -> float | None:
    """Return seconds since page was cached, or None if not cached."""
    data = _read_json(_page_path(feed_key, page))
    if not data:
        return None
    return time.time() - data.get("_cached_at", 0)


def invalidate_feed(feed_key: str) -> None:
    """Remove all pages + stash for a feed key."""
    with _write_lock:
        for f in CACHE_DIR.glob(f"feed_{feed_key}_p*.json"):
            f.unlink(missing_ok=True)
        _stash_path(feed_key).unlink(missing_ok=True)


def invalidate_page(feed_key: str, page: int) -> None:
    _page_path(feed_key, page).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Page-1 stash (instant cold-start load)
# ---------------------------------------------------------------------------

def get_stash(feed_key: str) -> list[dict]:
    data = _read_json(_stash_path(feed_key))
    return data if isinstance(data, list) else []


def put_stash(feed_key: str, entries: list[dict]) -> None:
    _write_json(_stash_path(feed_key), entries[:12])


def clear_stash(feed_key: str) -> None:
    _stash_path(feed_key).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Thumbnail cache
# ---------------------------------------------------------------------------

def thumb_path(video_id: str) -> Path:
    return CACHE_DIR / "thumbs" / f"{video_id}.jpg"


def has_thumb(video_id: str) -> bool:
    return thumb_path(video_id).exists()


# ---------------------------------------------------------------------------
# SponsorBlock segment cache
# ---------------------------------------------------------------------------

def _sb_path(video_id: str) -> Path:
    return CACHE_DIR / "sb" / f"{video_id}.json"


def get_sb(video_id: str, ttl: int = 3600) -> list[dict] | None:
    data = _read_json(_sb_path(video_id))
    if data is None:
        return None
    age = time.time() - data.get("_cached_at", 0)
    if age > ttl:
        return None
    return data.get("segments", [])


def put_sb(video_id: str, segments: list[dict]) -> None:
    _write_json(_sb_path(video_id), {"_cached_at": time.time(), "segments": segments})


# ---------------------------------------------------------------------------
# Quality negotiation memory
# ---------------------------------------------------------------------------

def _quality_path(video_id: str, mode: str) -> Path:
    return CACHE_DIR / "quality" / f"{video_id}_{mode}.txt"


def get_last_quality(video_id: str, mode: str) -> str | None:
    try:
        return _quality_path(video_id, mode).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def set_last_quality(video_id: str, mode: str, fmt: str) -> None:
    path = _quality_path(video_id, mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fmt, encoding="utf-8")


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def prune_old_thumbnails(max_age_days: int = 7, max_count: int = 300) -> None:
    _prune_dir(CACHE_DIR / "thumbs", max_age_days * 86400, max_count)


def prune_old_videos(max_age_days: int = 3, max_count: int = 400) -> None:
    _prune_dir(CACHE_DIR / "videos", max_age_days * 86400, max_count)


def prune_old_sb(max_age_days: int = 1) -> None:
    _prune_dir(CACHE_DIR / "sb", max_age_days * 86400, 10000)


def _prune_dir(directory: Path, max_age_secs: float, max_count: int) -> None:
    if not directory.exists():
        return
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
    now = time.time()
    for f in files:
        if now - f.stat().st_mtime > max_age_secs:
            f.unlink(missing_ok=True)
    files = [f for f in files if f.exists()]
    for f in files[:-max_count]:
        f.unlink(missing_ok=True)


def clear_all() -> None:
    """Wipe entire cache directory.  Used by --clear-cache CLI flag."""
    import shutil
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
