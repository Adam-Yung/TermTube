"""Disk cache for video metadata, feed id lists, suppression state and the home stash."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path

from src import logger
from src.entries import Entry
from src.plat import atomic_write, get_cache_dir

CACHE_DIR = get_cache_dir()
THUMB_DIR = CACHE_DIR / "thumbs"
VIDEO_DIR = CACHE_DIR / "videos"

# Playlist copies; pruning never touches these.
PLAYLIST_VIDEO_DIR = CACHE_DIR / "playlist_videos"
PLAYLIST_THUMB_DIR = CACHE_DIR / "playlist_thumbs"

_SUPPRESSED_PATH = CACHE_DIR / "suppressed.json"

_write_lock = threading.Lock()


def _ensure_dirs() -> None:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    PLAYLIST_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    PLAYLIST_THUMB_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


def _atomic_write(path: Path, text: str) -> None:
    """``plat.atomic_write`` for cache files, which are best effort: a failed write is dropped."""
    try:
        atomic_write(path, text.encode("utf-8"))
    except OSError:
        pass


class Cache:
    _RAM_CACHE_MAX = 64

    def __init__(self, ttl_map: dict[str, int]) -> None:
        self._ttl = ttl_map
        self._suppressed: OrderedDict[str, None] = OrderedDict()
        self._focus_counts: dict[str, int] = {}
        self._suppression_loaded = False
        self._suppression_lock = threading.Lock()
        self._ram_cache: OrderedDict[str, dict] = OrderedDict()
        self._ram_lock = threading.Lock()

    def _ram_put(self, video_id: str, data: dict) -> None:
        with self._ram_lock:
            self._ram_cache[video_id] = data
            if len(self._ram_cache) > self._RAM_CACHE_MAX:
                self._ram_cache.popitem(last=False)

    def get_video(self, video_id: str) -> Entry | None:
        """Cached entry within the ``metadata`` TTL, else None. Checks RAM, then disk."""
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
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data.get("_cached_at", 0)
            ttl = self._ttl.get("metadata", 86400)
            if age > ttl:
                return None
            self._ram_put(video_id, data)
            return data
        except (json.JSONDecodeError, OSError):
            return None

    # Large yt-dlp fields never read back; stripping them cuts a full-fetch entry from ~48 KB to ~2 KB.
    _FAT_FIELDS = frozenset({
        "formats",
        "requested_formats",
        "requested_downloads",
        "automatic_captions",
        "subtitles",
        "heatmap",
        "fragments",
    })

    def put_video(self, entry: Entry) -> None:
        vid = entry.get("id") or entry.get("webpage_url_basename")
        if not vid:
            return
        slim = {k: v for k, v in entry.items() if k not in self._FAT_FIELDS}
        slim["_cached_at"] = time.time()
        path = VIDEO_DIR / f"{vid}.json"
        with _write_lock:
            _atomic_write(path, json.dumps(slim, ensure_ascii=False))
        self._ram_put(vid, slim)
        logger.debug("cache.put_video %s (%d keys)", vid, len(slim))

    def get_video_raw(self, video_id: str) -> Entry | None:
        """Cached entry regardless of TTL, falling back to the pinned playlist copy."""
        with self._ram_lock:
            if video_id in self._ram_cache:
                self._ram_cache.move_to_end(video_id)
                return self._ram_cache[video_id]

        path = VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            path = PLAYLIST_VIDEO_DIR / f"{video_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._ram_put(video_id, data)
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def get_feed(self, key: str) -> list[str] | None:
        """Video ids of a feed, or None if missing or past its TTL (default 1 h)."""
        path = CACHE_DIR / f"feed_{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data.get("_cached_at", 0)
            if age > self._ttl.get(key, 3600):
                return None
            return data.get("ids", [])
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

    def _load_suppressed(self) -> None:
        """Load suppression state from disk, once per process."""
        with self._suppression_lock:
            if self._suppression_loaded:
                return
            self._suppression_loaded = True
            if not _SUPPRESSED_PATH.exists():
                return
            try:
                data = json.loads(_SUPPRESSED_PATH.read_text(encoding="utf-8"))
                self._suppressed = OrderedDict.fromkeys(data.get("ids", []))
                self._focus_counts = dict(data.get("focus_counts", {}))
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
        """Count a focus; the third suppresses the video. Counts stay in memory until a suppression flushes."""
        self._load_suppressed()
        with self._suppression_lock:
            if video_id in self._suppressed:
                return
            count = self._focus_counts.get(video_id, 0) + 1
            self._focus_counts[video_id] = count
            if count >= 3:
                self._suppressed[video_id] = None
                self._save_suppressed()
                logger.debug("cache.register_focus suppressing %s after %d focuses", video_id, count)
            self._prune_focus_counts()

    def _prune_focus_counts(self) -> None:
        """Cap ``_focus_counts`` at 5000: drop suppressed ids first, then the lowest counts."""
        if len(self._focus_counts) <= 5000:
            return
        self._focus_counts = {
            k: v for k, v in self._focus_counts.items()
            if k not in self._suppressed
        }
        if len(self._focus_counts) <= 5000:
            return
        sorted_items = sorted(self._focus_counts.items(), key=lambda x: x[1])
        keep = sorted_items[len(sorted_items) - 5000:]
        self._focus_counts = dict(keep)

    def suppress_video(self, video_id: str) -> None:
        """Suppress a video now. Past 2000 suppressed ids the oldest are evicted down to 1500."""
        self._load_suppressed()
        with self._suppression_lock:
            if video_id not in self._suppressed:
                self._suppressed[video_id] = None
                if len(self._suppressed) > 2000:
                    while len(self._suppressed) > 1500:
                        self._suppressed.popitem(last=False)
                self._save_suppressed()
                logger.debug("cache.suppress_video %s", video_id)

    def is_suppressed(self, video_id: str) -> bool:
        self._load_suppressed()
        return video_id in self._suppressed

    _STASH_SIZE = 20

    @property
    def _stash_path(self) -> Path:
        return CACHE_DIR / "feed_home_stash.json"

    def get_home_stash(self) -> list[Entry]:
        """The previous session's stashed home entries (first unseen page); [] on any error."""
        path = self._stash_path
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                return []
            return entries[: self._STASH_SIZE]
        except (json.JSONDecodeError, OSError):
            return []

    def put_home_stash(self, entries: list[Entry]) -> None:
        """Write up to ``_STASH_SIZE`` entries; the caller backfills so the next boot gets a full page."""
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
        """Delete the stash file."""
        try:
            self._stash_path.unlink(missing_ok=True)
            logger.debug("cache.clear_home_stash")
        except OSError:
            pass

    def clear_feed(self, key: str) -> None:
        path = CACHE_DIR / f"feed_{key}.json"
        try:
            path.unlink(missing_ok=True)
            logger.debug("cache.clear_feed %s", key)
        except OSError:
            pass

    def clear_all(self) -> int:
        """Delete cached feeds, video metadata and thumbnails (RAM copies too). Returns the number of files removed."""
        counts = []
        for directory, pattern in ((CACHE_DIR, "feed_*.json"), (VIDEO_DIR, "*.json"), (THUMB_DIR, "*.jpg")):
            files = list(directory.glob(pattern))
            for f in files:
                f.unlink(missing_ok=True)
            counts.append(len(files))
        with self._ram_lock:
            self._ram_cache.clear()
        feeds, videos, thumbs = counts
        logger.info("cache.clear_all: %d feeds, %d videos, %d thumbnails", feeds, videos, thumbs)
        return sum(counts)

    @staticmethod
    def _prune_dir(directory: Path, pattern: str, max_age_days: int | None, max_count: int) -> tuple[int, int]:
        """Delete files older than ``max_age_days`` (if given), then the oldest by mtime beyond ``max_count``.

        Returns ``(expired, capped)``.
        """
        cutoff = time.time() - max_age_days * 86400 if max_age_days is not None else None
        files: list[tuple[float, Path]] = []
        expired = 0
        for f in directory.glob(pattern):
            try:
                mtime = f.stat().st_mtime
                if cutoff is not None and mtime < cutoff:
                    f.unlink(missing_ok=True)
                    expired += 1
                else:
                    files.append((mtime, f))
            except OSError:
                pass
        capped = max(0, len(files) - max_count)
        files.sort()
        for _, f in files[:capped]:
            f.unlink(missing_ok=True)
        return expired, capped

    def prune_video_cache_fifo(self, max_count: int = 100) -> None:
        """Cap video metadata files at ``max_count``, evicting the oldest by mtime."""
        _, capped = self._prune_dir(VIDEO_DIR, "*.json", None, max_count)
        if capped:
            logger.debug("prune_video_cache_fifo: evicted %d", capped)

    def prune_old_thumbnails(self, max_age_days: int = 7, max_count: int = 300) -> None:
        expired, capped = self._prune_dir(THUMB_DIR, "*.jpg", max_age_days, max_count)
        logger.debug("prune_old_thumbnails: %d expired, %d capped", expired, capped)

    def prune_old_videos(self, max_age_days: int = 3, max_count: int = 100) -> None:
        """mtime is the cache age: ``put_video`` always rewrites the file."""
        expired, capped = self._prune_dir(VIDEO_DIR, "*.json", max_age_days, max_count)
        logger.debug("prune_old_videos: %d expired, %d capped", expired, capped)

    def pin_video(self, video_id: str, entry: Entry | None = None) -> None:
        """Copy ``entry`` (default: the cached entry) into the playlist cache that pruning skips."""
        if entry is None:
            entry = self.get_video_raw(video_id)
        if entry is None:
            return
        entry = {k: v for k, v in entry.items() if k not in self._FAT_FIELDS}
        dest = PLAYLIST_VIDEO_DIR / f"{video_id}.json"
        with _write_lock:
            _atomic_write(dest, json.dumps(entry, ensure_ascii=False))
        logger.debug("cache.pin_video %s", video_id)

    def pin_thumb(self, video_id: str, source: Path | None = None) -> None:
        """Copy the thumbnail (default: the cached one, or ``source``) into the playlist cache that pruning skips."""
        src = source or THUMB_DIR / f"{video_id}.jpg"
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
        """Remove the video and thumbnail from the playlist cache."""
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
        """Pin every video in any playlist (startup migration; skips already-pinned)."""
        from src import playlist
        pinned = 0
        for vid_id in playlist.all_video_ids():
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
