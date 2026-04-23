"""Disk-based cache with per-key TTL."""

from __future__ import annotations
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "myyoutube"
THUMB_DIR = CACHE_DIR / "thumbs"
VIDEO_DIR = CACHE_DIR / "videos"


def _ensure_dirs() -> None:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


class Cache:
    def __init__(self, ttl_map: dict[str, int]) -> None:
        self._ttl = ttl_map  # e.g. {"home": 3600, "metadata": 86400}

    # ── Video metadata ────────────────────────────────────────────────────────

    def get_video(self, video_id: str) -> dict | None:
        path = VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            age = time.time() - data.get("_cached_at", 0)
            ttl = self._ttl.get("metadata", 86400)
            if age > ttl:
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def put_video(self, entry: dict) -> None:
        vid = entry.get("id") or entry.get("webpage_url_basename")
        if not vid:
            return
        entry["_cached_at"] = time.time()
        path = VIDEO_DIR / f"{vid}.json"
        try:
            path.write_text(json.dumps(entry, ensure_ascii=False))
        except OSError:
            pass

    def get_video_raw(self, video_id: str) -> dict | None:
        """Get cached entry regardless of TTL (used by preview script)."""
        path = VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    # ── Feed lists ────────────────────────────────────────────────────────────

    def get_feed(self, key: str) -> list[str] | None:
        """Returns list of video IDs for a feed, or None if stale/missing."""
        path = CACHE_DIR / f"feed_{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            age = time.time() - data.get("_cached_at", 0)
            if age > self._ttl.get(key, 3600):
                return None
            return data.get("ids", [])
        except (json.JSONDecodeError, OSError):
            return None

    def put_feed(self, key: str, ids: list[str]) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        try:
            path.write_text(json.dumps({"_cached_at": time.time(), "ids": ids}))
        except OSError:
            pass

    # ── Thumbnails ────────────────────────────────────────────────────────────

    def thumb_path(self, video_id: str) -> Path:
        return THUMB_DIR / f"{video_id}.jpg"

    def has_thumb(self, video_id: str) -> bool:
        return self.thumb_path(video_id).exists()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def clear_feed(self, key: str) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        if path.exists():
            path.unlink()

    def clear_all(self) -> None:
        for f in CACHE_DIR.glob("feed_*.json"):
            f.unlink(missing_ok=True)
        for f in VIDEO_DIR.glob("*.json"):
            f.unlink(missing_ok=True)
