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
    """Run cmd, yield each stdout line parsed as JSON. Ignores non-JSON lines."""
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
    # ── Serve from cache ──────────────────────────────────────────────────────
    if feed_key:
        cached_ids = cache.get_feed(feed_key)
        if cached_ids:
            logger.debug("stream_flat cache hit for feed '%s' (%d ids)", feed_key, len(cached_ids))
            count = 0
            for vid_id in cached_ids:
                entry = cache.get_video_raw(vid_id)
                if entry:
                    if on_entry:
                        on_entry(entry)
                    yield entry
                    count += 1
            if count > 0:
                return  # Served entirely from cache

    # ── Fresh fetch from yt-dlp ───────────────────────────────────────────────
    logger.debug("stream_flat fetching fresh: %s", url)
    cmd = ["yt-dlp", *_FAST_FLAGS, *cookie_args(config), url]
    seen_ids: list[str] = []

    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        _normalise_entry(entry)
        cache.put_video(entry)
        vid = entry.get("id", "")
        if vid:
            seen_ids.append(vid)
        if on_entry:
            on_entry(entry)
        yield entry

    # Save feed index for instant next load
    if feed_key and seen_ids:
        cache.put_feed(feed_key, seen_ids)
        logger.debug("Saved feed index '%s' with %d ids", feed_key, len(seen_ids))


def stream_search(
    query: str,
    config,
    cache: Cache,
    *,
    count: int = 40,
) -> Generator[dict, None, None]:
    """
    Stream search results for query.
    Results are cached by query hash; repeat searches are instant.
    """
    # Cache key = short hash of the query string
    cache_key = "search_" + hashlib.md5(query.lower().strip().encode()).hexdigest()[:10]

    # ── Serve from cache ──────────────────────────────────────────────────────
    cached_ids = cache.get_feed(cache_key)
    if cached_ids:
        logger.debug("stream_search cache hit for '%s'", query)
        count_served = 0
        for vid_id in cached_ids:
            entry = cache.get_video_raw(vid_id)
            if entry:
                yield entry
                count_served += 1
        if count_served > 0:
            return

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
        _normalise_entry(entry)
        cache.put_video(entry)
        vid = entry.get("id", "")
        if vid:
            seen_ids.append(vid)
        yield entry

    if seen_ids:
        cache.put_feed(cache_key, seen_ids)


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

def download_video(video_id: str, config, *, on_progress: Callable[[str], None] | None = None) -> bool:
    """Download video to config.video_dir. Returns True on success."""
    config.video_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"

    quality = config.preferred_quality
    fmt = "bestvideo+bestaudio/best" if quality == "best" else f"bestvideo[height<={quality}]+bestaudio/best"

    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", str(config.video_dir / config.video_format),
        "--write-info-json",
        "--write-thumbnail",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    logger.debug("download_video: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def download_audio(video_id: str, config, *, on_progress: Callable[[str], None] | None = None) -> bool:
    """Download audio-only to config.audio_dir. Returns True on success."""
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        "yt-dlp",
        "--format", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", str(config.audio_dir / config.audio_format),
        "--write-info-json",
        "--write-thumbnail",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    logger.debug("download_audio: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def get_stream_url(video_id: str, config, *, audio_only: bool = False) -> str | None:
    """Get a direct streamable URL for mpv (avoids re-fetching inside mpv)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    fmt = "bestaudio/best" if audio_only else "bestvideo+bestaudio/best"
    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--get-url",
        "--no-warnings",
        "--quiet",
        *cookie_args(config),
        url,
    ]
    logger.debug("get_stream_url: %s", url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[0]
    logger.warning("get_stream_url failed for %s: %s", video_id, result.stderr.strip())
    return None


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


def open_in_browser(video_id: str) -> None:
    """Open the video in the default system browser."""
    import webbrowser
    webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")


def subscribe_channel(channel_url: str, config) -> bool:
    """Subscribe to a channel (requires authenticated session)."""
    import webbrowser
    webbrowser.open(channel_url)
    return True
