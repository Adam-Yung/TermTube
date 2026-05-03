"""Disk-based cache with per-key TTL."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from src import logger

CACHE_DIR = Path.home() / ".cache" / "termtube"
THUMB_DIR = CACHE_DIR / "thumbs"
VIDEO_DIR = CACHE_DIR / "videos"

_SUPPRESSED_PATH = CACHE_DIR / "suppressed.json"

# Lock protecting all cache file writes so concurrent enrichment threads don't
# interleave partial writes on the same file.
_write_lock = threading.Lock()


def _ensure_dirs() -> None:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically via a tmp file + os.replace()."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


class Cache:
    def __init__(self, ttl_map: dict[str, int]) -> None:
        self._ttl = ttl_map  # e.g. {"home": 3600, "metadata": 86400}
        self._suppressed: set[str] = set()
        self._focus_counts: dict[str, int] = {}
        self._suppression_loaded = False
        self._suppression_lock = threading.Lock()

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

    # Fields from a full yt-dlp fetch that are large and never read back from
    # cache.  Stripping them cuts average JSON size from ~48 KB to ~2 KB.
    _FAT_FIELDS = frozenset({
        "formats",
        "requested_formats",
        "requested_downloads",
        "automatic_captions",
        "subtitles",
        "heatmap",
        "fragments",
    })

    def put_video(self, entry: dict) -> None:
        vid = entry.get("id") or entry.get("webpage_url_basename")
        if not vid:
            return
        slim = {k: v for k, v in entry.items() if k not in self._FAT_FIELDS}
        slim["_cached_at"] = time.time()
        path = VIDEO_DIR / f"{vid}.json"
        with _write_lock:
            _atomic_write(path, json.dumps(slim, ensure_ascii=False))
        logger.debug("cache.put_video %s (%d keys)", vid, len(slim))

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

    def get_feed_stale(self, key: str) -> list[str] | None:
        """Return cached feed IDs even if TTL has expired (stale-while-revalidate).
        Returns None only if no cache file exists at all."""
        path = CACHE_DIR / f"feed_{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return data.get("ids") or None
        except (json.JSONDecodeError, OSError):
            return None

    def is_feed_fresh(self, key: str) -> bool:
        """True if the feed cache exists and is within TTL."""
        return self.get_feed(key) is not None

    def put_feed(self, key: str, ids: list[str]) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        with _write_lock:
            _atomic_write(path, json.dumps({"_cached_at": time.time(), "ids": ids}))
        logger.debug("cache.put_feed %s (%d ids)", key, len(ids))

    # ── Thumbnails ────────────────────────────────────────────────────────────

    def thumb_path(self, video_id: str) -> Path:
        return THUMB_DIR / f"{video_id}.jpg"

    def has_thumb(self, video_id: str) -> bool:
        return self.thumb_path(video_id).exists()

    # ── Home feed suppression ─────────────────────────────────────────────────

    def _load_suppressed(self) -> None:
        """Load suppression set from disk (once per process)."""
        with self._suppression_lock:
            if self._suppression_loaded:
                return
            self._suppression_loaded = True
            if not _SUPPRESSED_PATH.exists():
                return
            try:
                data = json.loads(_SUPPRESSED_PATH.read_text())
                self._suppressed = set(data.get("ids", []))
                self._focus_counts = {
                    k: v for k, v in data.get("focus_counts", {}).items()
                }
            except (json.JSONDecodeError, OSError):
                pass

    def _save_suppressed(self) -> None:
        with _write_lock:
            _atomic_write(
                _SUPPRESSED_PATH,
                json.dumps(
                    {
                        "ids": list(self._suppressed),
                        "focus_counts": self._focus_counts,
                    },
                    ensure_ascii=False,
                ),
            )

    def register_focus(self, video_id: str) -> None:
        """Increment focus count for a video; suppress after 3 focuses.

        Counts are accumulated in memory and only flushed to disk when the
        suppression threshold is crossed — no disk I/O on every cursor move.
        """
        self._load_suppressed()
        if video_id in self._suppressed:
            return
        count = self._focus_counts.get(video_id, 0) + 1
        self._focus_counts[video_id] = count
        if count >= 3:
            self._suppressed.add(video_id)
            self._save_suppressed()  # only write when threshold is crossed
            logger.debug("cache.register_focus suppressing %s after %d focuses", video_id, count)

    def suppress_video(self, video_id: str) -> None:
        """Immediately suppress a video (e.g. after listening to it)."""
        self._load_suppressed()
        if video_id not in self._suppressed:
            self._suppressed.add(video_id)
            self._save_suppressed()
            logger.debug("cache.suppress_video %s", video_id)

    def is_suppressed(self, video_id: str) -> bool:
        self._load_suppressed()
        return video_id in self._suppressed

    # ── Helpers ───────────────────────────────────────────────────────────────

    def clear_feed(self, key: str) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        if path.exists():
            path.unlink()
            logger.debug("cache.clear_feed %s", key)

    def clear_all(self) -> None:
        feeds = videos = thumbs = 0
        for f in CACHE_DIR.glob("feed_*.json"):
            f.unlink(missing_ok=True); feeds += 1
        for f in VIDEO_DIR.glob("*.json"):
            f.unlink(missing_ok=True); videos += 1
        for f in THUMB_DIR.glob("*.jpg"):
            f.unlink(missing_ok=True); thumbs += 1
        logger.info("cache.clear_all: %d feeds, %d videos, %d thumbnails", feeds, videos, thumbs)

    def prune_old_thumbnails(self, max_age_days: int = 7, max_count: int = 300) -> None:
        """Delete thumbnails older than max_age_days, then enforce max_count cap."""
        cutoff = time.time() - max_age_days * 86400
        files: list[tuple[float, Path]] = []
        deleted = 0
        for f in THUMB_DIR.glob("*.jpg"):
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
                    deleted += 1
                else:
                    files.append((mtime, f))
            except OSError:
                pass
        # Hard cap: evict oldest by access time if still over limit.
        capped = 0
        if len(files) > max_count:
            files.sort()
            for _, f in files[: len(files) - max_count]:
                f.unlink(missing_ok=True)
                capped += 1
        logger.debug("prune_old_thumbnails: %d expired, %d capped, %d kept",
                     deleted, capped, max(0, len(files) - capped))

    def prune_old_videos(self, max_age_days: int = 3, max_count: int = 400) -> None:
        """Delete video JSONs older than max_age_days, then enforce max_count cap.

        Uses the _cached_at timestamp stored inside the JSON rather than st_mtime.
        st_mtime is reset by enrich_in_background on every enrichment write, which
        would otherwise make every enriched file appear perpetually fresh.
        """
        now = time.time()
        cutoff = now - max_age_days * 86400
        files: list[tuple[float, Path]] = []
        deleted = 0
        for f in VIDEO_DIR.glob("*.json"):
            try:
                cached_at = json.loads(f.read_text()).get("_cached_at", 0)
                if cached_at < cutoff:
                    f.unlink(missing_ok=True)
                    deleted += 1
                else:
                    files.append((cached_at, f))
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        # Hard cap: evict oldest by _cached_at if still over limit.
        capped = 0
        if len(files) > max_count:
            files.sort()
            for _, f in files[: len(files) - max_count]:
                f.unlink(missing_ok=True)
                capped += 1
        logger.debug("prune_old_videos: %d expired, %d capped, %d kept",
                     deleted, capped, max(0, len(files) - capped))
