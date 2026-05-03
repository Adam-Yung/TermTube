"""yt-dlp interface — all yt-dlp subprocess calls live here.

Progressive streaming design:
  stream_flat()    →  cache-first: yields from disk cache instantly if fresh,
                      otherwise fetches from yt-dlp and saves feed index.
  stream_search()  →  same, keyed by query hash.
  fetch_full()     →  fetches complete metadata for one video (slower).
  enrich_in_background() → parallel background fetch for multiple videos.
"""

from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Generator, Iterable

from src.cache import Cache
from src import logger

# ── Active process registry (for clean shutdown) ──────────────────────────────

_active_procs: set[subprocess.Popen] = set()  # type: ignore[type-arg]
_active_procs_lock = threading.Lock()


def kill_all_active() -> None:
    """Kill every yt-dlp subprocess that is currently streaming.

    Called by the TUI before exit so that worker threads blocked on subprocess
    stdout unblock immediately, preventing the app from hanging on quit.
    """
    with _active_procs_lock:
        procs = list(_active_procs)
        _active_procs.clear()
    if procs:
        logger.debug("kill_all_active: terminating %d yt-dlp procs", len(procs))
    for proc in procs:
        try:
            proc.kill()
        except Exception:
            pass


# ── Feed URLs ─────────────────────────────────────────────────────────────────

FEED_URLS = {
    "home":          "https://www.youtube.com/feed/recommended",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}

# ── Flags that make flat-playlist fetches fast ────────────────────────────────
_FAST_FLAGS = [
    "--flat-playlist",
    "--dump-json",
    "--no-warnings",
    "--quiet",
    "--extractor-args", "youtube:skip=dash,hls",
    "--no-playlist-reverse",
]


# ── Cookie helper ─────────────────────────────────────────────────────────────

def cookie_args(config) -> list[str]:
    """Return yt-dlp --cookies or --cookies-from-browser flags."""
    return config.cookie_args


# ── Entry normalisation ───────────────────────────────────────────────────────

def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry dict."""
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        jpg = [t for t in thumbs if "jpg" in t.get("url", "")]
        best = (jpg or thumbs)[-1]
        return best.get("url", "")
    return entry.get("thumbnail", "")


_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _is_playable_video(entry: dict) -> bool:
    """
    Return True only for proper YouTube video entries.
    Filters out playlists, channels, YouTube Mix (RD...), and other non-video results
    that yt-dlp --flat-playlist sometimes includes.
    """
    vid = entry.get("id", "")
    # Standard YouTube video IDs are exactly 11 URL-safe base64 chars
    if not _VIDEO_ID_RE.match(vid):
        return False
    # Explicit type field
    etype = entry.get("_type", "video")
    if etype in ("playlist", "channel"):
        return False
    return True


def _normalise_entry(entry: dict) -> dict:
    """Ensure flat-playlist entries have 'thumbnail' and 'webpage_url' fields."""
    entry.setdefault("webpage_url", f"https://www.youtube.com/watch?v={entry.get('id', '')}")
    if not entry.get("thumbnail"):
        url = _best_thumb_url(entry)
        if url:
            entry["thumbnail"] = url
    return entry


# ── Low-level streaming ───────────────────────────────────────────────────────

def _stream_json_lines(cmd: list[str], *, capture_stderr: bool = False) -> Generator[dict, None, None]:
    """Run cmd, yield each stdout line parsed as JSON. Ignores non-JSON lines.

    The subprocess is registered in _active_procs so that kill_all_active()
    can terminate it immediately on quit, unblocking the worker thread.
    """
    logger.debug("yt-dlp cmd: %s", " ".join(cmd))
    try:
        stderr_dest = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_dest,
            text=True,
            bufsize=1,
        )
        with _active_procs_lock:
            _active_procs.add(proc)
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
            proc.wait()
            if capture_stderr and proc.stderr:
                err = proc.stderr.read()
                if err.strip():
                    logger.debug("yt-dlp stderr: %s", err.strip())
                if proc.returncode != 0:
                    logger.warning("yt-dlp exited %d: %s", proc.returncode, err.strip())
        finally:
            with _active_procs_lock:
                _active_procs.discard(proc)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Install with: brew install yt-dlp")


# ── Public streaming API ──────────────────────────────────────────────────────

def stream_flat(
    url: str,
    config,
    cache: Cache,
    *,
    feed_key: str | None = None,
    on_entry: Callable[[dict], None] | None = None,
) -> Generator[dict, None, None]:
    """
    Stream basic video entries from a URL using --flat-playlist.

    Cache-first: if feed_key is given and the cache is fresh, entries are
    yielded instantly from disk (no network call). Otherwise, fetches from
    yt-dlp and saves the feed index for next time.
    """
    # Minimum number of entries to consider a feed cache valid.
    # If the previous fetch was interrupted early or auth failed, the cache
    # would have too few entries — treat that as a miss and refetch.
    _MIN_FEED_COUNT = 15

    # ── Serve from cache ──────────────────────────────────────────────────────
    if feed_key:
        cached_ids = cache.get_feed(feed_key)
        if cached_ids and len(cached_ids) >= _MIN_FEED_COUNT:
            logger.debug("stream_flat cache hit for feed '%s' (%d ids)", feed_key, len(cached_ids))
            count = 0
            for vid_id in cached_ids:
                entry = cache.get_video_raw(vid_id)
                if entry:
                    if on_entry:
                        on_entry(entry)
                    yield entry
                    count += 1
            if count >= _MIN_FEED_COUNT:
                return  # Served entirely from cache
            # Too few video JSONs present — fall through to fresh fetch
            logger.debug("stream_flat: only %d/%d video JSONs found, refetching", count, len(cached_ids))
        elif cached_ids:
            logger.debug("stream_flat: cached feed '%s' too small (%d ids < %d), refetching",
                         feed_key, len(cached_ids), _MIN_FEED_COUNT)
            cache.clear_feed(feed_key)

    # ── Fresh fetch from yt-dlp ───────────────────────────────────────────────
    logger.debug("stream_flat fetching fresh: %s", url)
    cmd = ["yt-dlp", *_FAST_FLAGS, *cookie_args(config), url]
    seen_ids: list[str] = []

    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        if not _is_playable_video(entry):
            logger.debug("stream_flat: skipping non-video entry id=%r type=%r",
                         entry.get("id"), entry.get("_type"))
            continue
        _normalise_entry(entry)
        cache.put_video(entry)
        vid = entry.get("id", "")
        if vid:
            seen_ids.append(vid)
        if on_entry:
            on_entry(entry)
        yield entry

    # Only save feed index if we got a reasonable number of entries.
    # This prevents caching an incomplete result from an interrupted or
    # unauthenticated fetch.
    if feed_key and len(seen_ids) >= _MIN_FEED_COUNT:
        cache.put_feed(feed_key, seen_ids)
        logger.debug("Saved feed index '%s' with %d ids", feed_key, len(seen_ids))
    elif feed_key and seen_ids:
        logger.debug("stream_flat: only %d results, not caching feed '%s'", len(seen_ids), feed_key)


def stream_search(
    query: str,
    config,
    cache: Cache,
    *,
    count: int = 50,
) -> Generator[dict, None, None]:
    """
    Stream search results for query.
    Results are cached by query hash; repeat searches are instant.
    """
    # Cache key = short hash of the query string
    cache_key = "search_" + hashlib.md5(query.lower().strip().encode()).hexdigest()[:10]
    _MIN_SEARCH_COUNT = 5  # Searches can legitimately have few results

    # ── Serve from cache ──────────────────────────────────────────────────────
    cached_ids = cache.get_feed(cache_key)
    if cached_ids and len(cached_ids) >= _MIN_SEARCH_COUNT:
        logger.debug("stream_search cache hit for '%s' (%d ids)", query, len(cached_ids))
        count_served = 0
        for vid_id in cached_ids:
            entry = cache.get_video_raw(vid_id)
            if entry:
                yield entry
                count_served += 1
        if count_served >= _MIN_SEARCH_COUNT:
            return
        logger.debug("stream_search: only %d/%d video JSONs found for '%s', refetching",
                     count_served, len(cached_ids), query)
    elif cached_ids:
        logger.debug("stream_search: stale small cache (%d ids) for '%s', refetching",
                     len(cached_ids), query)
        cache.clear_feed(cache_key)

    # ── Fresh fetch ───────────────────────────────────────────────────────────
    url = f"ytsearch{count}:{query}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--flat-playlist",
        "--extractor-args", "youtube:skip=dash,hls",
        *cookie_args(config),
        url,
    ]
    seen_ids: list[str] = []

    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        if not _is_playable_video(entry):
            continue
        _normalise_entry(entry)
        cache.put_video(entry)
        vid = entry.get("id", "")
        if vid:
            seen_ids.append(vid)
        yield entry

    if len(seen_ids) >= _MIN_SEARCH_COUNT:
        cache.put_feed(cache_key, seen_ids)
    elif seen_ids:
        logger.debug("stream_search: only %d results for '%s', not caching", len(seen_ids), query)


# ── Full metadata (for video detail page) ────────────────────────────────────

def fetch_full(video_id: str, config, cache: Cache) -> dict | None:
    """Fetch complete metadata for a single video. Returns cached if fresh."""
    cached = cache.get_video(video_id)
    if cached and cached.get("description") is not None:
        logger.debug("fetch_full cache hit: %s", video_id)
        return cached

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--skip-download",
        "--extractor-args", "youtube:skip=dash,hls",
        *cookie_args(config),
        url,
    ]
    logger.debug("fetch_full fetching: %s", video_id)
    results = list(_stream_json_lines(cmd, capture_stderr=logger.is_debug()))
    if not results:
        logger.warning("fetch_full got no data for %s — falling back to flat cache", video_id)
        return cache.get_video_raw(video_id)
    entry = results[0]
    _normalise_entry(entry)
    cache.put_video(entry)
    return entry


def enrich_in_background(
    video_ids: Iterable[str],
    config,
    cache: Cache,
    *,
    max_workers: int = 2,
    on_done: Callable[[str, dict], None] | None = None,
) -> None:
    """
    Fetch full metadata for video IDs in parallel background threads.
    Also pre-downloads thumbnails for enriched videos.
    on_done(video_id, entry) called when each finishes. Fire-and-forget.
    """
    ids = list(video_ids)
    if not ids:
        return

    logger.debug("enrich_in_background: %d videos, max_workers=%d", len(ids), max_workers)

    def _worker() -> None:
        from src.ui import thumbnail as _thumb
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fetch_full, vid, config, cache): vid for vid in ids}
            for future in as_completed(futures):
                vid = futures[future]
                try:
                    entry = future.result()
                    if entry:
                        # Pre-download thumbnail so preview is instant
                        thumb_url = entry.get("thumbnail", "")
                        if thumb_url and not _thumb._thumb_path(vid).exists():
                            _thumb.download(vid, thumb_url)
                        if on_done:
                            on_done(vid, entry)
                except Exception as exc:
                    logger.debug("enrich_in_background error for %s: %s", vid, exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ── Download ──────────────────────────────────────────────────────────────────

# ── Quality helpers ───────────────────────────────────────────────────────────

# (label, yt-dlp format string)
QUALITY_CHOICES: list[tuple[str, str]] = [
    ("best  (highest available)",          "bestvideo+bestaudio/best"),
    ("1080p (Full HD)",                    "bestvideo[height<=1080]+bestaudio/best"),
    ("720p  (HD)",                         "bestvideo[height<=720]+bestaudio/best"),
    ("480p  (SD)",                         "bestvideo[height<=480]+bestaudio/best"),
    ("360p  (low)",                        "bestvideo[height<=360]+bestaudio/best"),
    ("Audio only (best quality)",          "bestaudio/best"),
]

AUDIO_QUALITY_CHOICES: list[tuple[str, str]] = [
    ("best audio",   "bestaudio/best"),
    ("medium audio", "bestaudio[abr<=128]/bestaudio/best"),
]

_PROGRESS_RE = re.compile(r'\[download\]\s+([\d.]+)%')


def _run_download_with_progress(
    cmd: list[str],
    on_progress: Callable[[str, float], None] | None = None,
) -> bool:
    """Run a yt-dlp download command, streaming progress. Returns True on success."""
    logger.debug("download cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            m = _PROGRESS_RE.search(line)
            pct = float(m.group(1)) if m else -1.0
            if on_progress:
                on_progress(line, pct)
            elif pct >= 0:
                # Default: simple progress bar to stderr
                filled = int(pct / 2)
                bar = "█" * filled + "░" * (50 - filled)
                sys.stderr.write(f"\r  [{bar}] {pct:5.1f}%")
                sys.stderr.flush()
        if on_progress is None:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
        proc.wait()
        return proc.returncode == 0
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Install with: brew install yt-dlp")


def download_video_with_progress(
    video_id: str,
    config,
    *,
    quality_format: str = "",
    on_progress: Callable[[str, float], None] | None = None,
) -> bool:
    """Download video with live progress. quality_format overrides preferred_quality."""
    config.video_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"

    if quality_format:
        fmt = quality_format
    else:
        q = config.preferred_quality
        fmt = "bestvideo+bestaudio/best" if q == "best" else f"bestvideo[height<={q}]+bestaudio/best"

    logger.info("download_video %s (format=%s)", video_id, fmt)

    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", str(config.video_dir / config.video_format),
        "--write-info-json",
        "--write-thumbnail",
        "--newline",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    return _run_download_with_progress(cmd, on_progress)


def download_audio_with_progress(
    video_id: str,
    config,
    *,
    on_progress: Callable[[str, float], None] | None = None,
) -> bool:
    """Download audio with live progress."""
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("download_audio %s", video_id)

    cmd = [
        "yt-dlp",
        "--format", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", str(config.audio_dir / config.audio_format),
        "--write-info-json",
        "--write-thumbnail",
        "--newline",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    return _run_download_with_progress(cmd, on_progress)


