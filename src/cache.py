"""Disk-based cache with per-key TTL."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

from src import logger
from src.platform import get_cache_dir

CACHE_DIR = get_cache_dir()
THUMB_DIR = CACHE_DIR / "thumbs"
VIDEO_DIR = CACHE_DIR / "videos"

# Protected playlist cache — not subject to eviction
PLAYLIST_VIDEO_DIR = CACHE_DIR / "playlist_videos"
PLAYLIST_THUMB_DIR = CACHE_DIR / "playlist_thumbs"

_SUPPRESSED_PATH = CACHE_DIR / "suppressed.json"

# Lock protecting all cache file writes so concurrent enrichment threads don't
# interleave partial writes on the same file.
_write_lock = threading.Lock()


def _ensure_dirs() -> None:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    PLAYLIST_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    PLAYLIST_THUMB_DIR.mkdir(parents=True, exist_ok=True)


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
    _RAM_CACHE_MAX = 64

    def __init__(self, ttl_map: dict[str, int]) -> None:
        self._ttl = ttl_map  # e.g. {"home": 3600, "metadata": 86400}
        self._suppressed: set[str] = set()
        self._focus_counts: dict[str, int] = {}
        self._suppression_loaded = False
        self._suppression_lock = threading.Lock()
        self._ram_cache: OrderedDict[str, dict] = OrderedDict()
        self._ram_lock = threading.Lock()

    # ── Video metadata ────────────────────────────────────────────────────────

    def get_video(self, video_id: str) -> dict | None:
        with self._ram_lock:
            if video_id in self._ram_cache:
                self._ram_cache.move_to_end(video_id)
                data = self._ram_cache[video_id]
                age = time.time() - data.get("_cached_at", 0)
                ttl = self._ttl.get("metadata", 86400)
                if age <= ttl:
                    return data
                del self._ram_cache[video_id]

        path = VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            age = time.time() - data.get("_cached_at", 0)
            ttl = self._ttl.get("metadata", 86400)
            if age > ttl:
                return None
            with self._ram_lock:
                self._ram_cache[video_id] = data
                if len(self._ram_cache) > self._RAM_CACHE_MAX:
                    self._ram_cache.popitem(last=False)
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
        with self._ram_lock:
            self._ram_cache[vid] = slim
            if len(self._ram_cache) > self._RAM_CACHE_MAX:
                self._ram_cache.popitem(last=False)
        logger.debug("cache.put_video %s (%d keys)", vid, len(slim))

    def get_video_raw(self, video_id: str) -> dict | None:
        """Get cached entry regardless of TTL (used by preview script)."""
        path = VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            path = PLAYLIST_VIDEO_DIR / f"{video_id}.json"
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

    def feed_age(self, key: str) -> float | None:
        """Return age (seconds) of the cached feed file, or None if no cache exists."""
        path = CACHE_DIR / f"feed_{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            cached_at = data.get("_cached_at", 0)
            if not cached_at:
                return None
            return max(0.0, time.time() - cached_at)
        except (json.JSONDecodeError, OSError):
            return None

    def put_feed(self, key: str, ids: list[str]) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        with _write_lock:
            _atomic_write(path, json.dumps({"_cached_at": time.time(), "ids": ids}))
        logger.debug("cache.put_feed %s (%d ids)", key, len(ids))

    # ── Thumbnails ────────────────────────────────────────────────────────────

    def thumb_path(self, video_id: str) -> Path:
        path = THUMB_DIR / f"{video_id}.jpg"
        if not path.exists():
            playlist_path = PLAYLIST_THUMB_DIR / f"{video_id}.jpg"
            if playlist_path.exists():
                return playlist_path
        return path

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

    # ── Home-feed quick-start stash ───────────────────────────────────────────
    # Up to _STASH_SIZE full entry dicts from the previous session's unconsumed
    # buffer are saved here so the next boot can show something instantly while
    # the fresh 100-entry background fetch is running.

    _STASH_SIZE = 20

    @property
    def _stash_path(self) -> Path:
        return CACHE_DIR / "feed_home_stash.json"

    def get_home_stash(self) -> list[dict]:
        """Return up to _STASH_SIZE stashed entries from the previous session.

        These represent the first unseen page from last session, ensuring fresh
        content on every boot. Never raises; returns [] on any error.
        """
        path = self._stash_path
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                return []
            return entries[: self._STASH_SIZE]
        except (json.JSONDecodeError, OSError):
            return []

    def put_home_stash(self, entries: list[dict]) -> None:
        """Atomically write up to _STASH_SIZE entries to the stash file.

        Called on exit with the first unseen page's entries. If fewer than
        _STASH_SIZE entries are provided, the caller should backfill so the
        user always gets a full page on next boot.
        """
        slim = entries[: self._STASH_SIZE]
        try:
            with _write_lock:
                _atomic_write(
                    self._stash_path,
                    json.dumps(
                        {"_cached_at": time.time(), "entries": slim},
                        ensure_ascii=False,
                    ),
                )
            logger.debug("cache.put_home_stash: %d entries", len(slim))
        except OSError:
            pass

    def clear_home_stash(self) -> None:
        """Delete the stash file (used by R-refresh)."""
        try:
            self._stash_path.unlink(missing_ok=True)
            logger.debug("cache.clear_home_stash")
        except OSError:
            pass

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

    def prune_video_cache_fifo(self, max_count: int = 100) -> None:
        """Enforce a hard cap on video metadata cache entries (FIFO by mtime).

        Evicts the oldest entries by file modification time until
        only max_count remain. Called after batch fetches to keep the
        cache lean.
        """
        files: list[tuple[float, Path]] = []
        for f in VIDEO_DIR.glob("*.json"):
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                pass
        if len(files) <= max_count:
            return
        files.sort()
        evict_count = len(files) - max_count
        for _, f in files[:evict_count]:
            f.unlink(missing_ok=True)
        logger.debug("prune_video_cache_fifo: evicted %d, kept %d", evict_count, max_count)

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

    def prune_old_videos(self, max_age_days: int = 3, max_count: int = 100) -> None:
        """Delete video JSONs older than max_age_days, then enforce max_count cap.

        Uses file mtime as a proxy for cache age. Since put_video() always
        creates a new file via atomic write, mtime reflects when the entry
        was last cached/refreshed.
        """
        now = time.time()
        cutoff = now - max_age_days * 86400
        files: list[tuple[float, Path]] = []
        deleted = 0
        for f in VIDEO_DIR.glob("*.json"):
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
                    deleted += 1
                else:
                    files.append((mtime, f))
            except OSError:
                pass
        # Hard cap: evict oldest by mtime if still over limit.
        capped = 0
        if len(files) > max_count:
            files.sort()
            for _, f in files[: len(files) - max_count]:
                f.unlink(missing_ok=True)
                capped += 1
        logger.debug("prune_old_videos: %d expired, %d capped, %d kept",
                     deleted, capped, max(0, len(files) - capped))

    # ── Playlist pinning (protected from eviction) ─────────────────────────────

    def pin_video(self, video_id: str, entry: dict | None = None) -> None:
        """Copy video metadata to the protected playlist cache.

        If entry is provided, writes it directly. Otherwise copies from
        the main video cache if available.
        """
        if entry is None:
            entry = self.get_video_raw(video_id)
        if entry is None:
            return
        dest = PLAYLIST_VIDEO_DIR / f"{video_id}.json"
        with _write_lock:
            _atomic_write(dest, json.dumps(entry, ensure_ascii=False))
        logger.debug("cache.pin_video %s", video_id)

    def pin_thumb(self, video_id: str) -> None:
        """Copy thumbnail to the protected playlist cache."""
        import shutil
        src = THUMB_DIR / f"{video_id}.jpg"
        if not src.exists():
            return
        dest = PLAYLIST_THUMB_DIR / f"{video_id}.jpg"
        if dest.exists():
            return
        try:
            shutil.copy2(src, dest)
            logger.debug("cache.pin_thumb %s", video_id)
        except OSError:
            pass

    def unpin_video(self, video_id: str) -> None:
        """Remove video from the protected playlist cache."""
        for path in (
            PLAYLIST_VIDEO_DIR / f"{video_id}.json",
            PLAYLIST_THUMB_DIR / f"{video_id}.jpg",
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.debug("cache.unpin_video %s", video_id)

    def pin_all_playlist_videos(self) -> None:
        """One-time migration: pin all videos currently in any playlist."""
        from src import playlist
        all_ids: set[str] = set()
        for name in playlist.list_names():
            all_ids.update(playlist.get_playlist(name))
        pinned = 0
        for vid_id in all_ids:
            dest = PLAYLIST_VIDEO_DIR / f"{vid_id}.json"
            if dest.exists():
                continue
            entry = self.get_video_raw(vid_id)
            if entry:
                self.pin_video(vid_id, entry)
                pinned += 1
            self.pin_thumb(vid_id)
        if pinned:
            logger.debug("cache.pin_all_playlist_videos: pinned %d entries", pinned)
