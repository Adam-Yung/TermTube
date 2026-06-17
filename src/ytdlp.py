"""yt-dlp interface — all yt-dlp subprocess calls live here.

Progressive streaming design:
  fetch_page_batch()  →  cache-first paged fetch: yields from disk cache instantly
                         if fresh, otherwise fetches from yt-dlp and saves feed index.
  fetch_search_batch() →  same, keyed by query hash.
  fetch_full()         →  fetches complete metadata for one video (slower).
                         Accepts on_proc_started so the caller can cancel the
                         subprocess if the user moves on before it completes.
"""

from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from typing import Callable, Generator

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

# Timeout (seconds) for waiting on yt-dlp stdout. If no data arrives within
# this window, we assume the process is hung and kill it.
_STREAM_READ_TIMEOUT_S = 30


def _stream_json_lines(
    cmd: list[str],
    *,
    capture_stderr: bool = False,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> Generator[dict, None, None]:
    """Run cmd, yield each stdout line parsed as JSON. Ignores non-JSON lines.

    The subprocess is registered in _active_procs so that kill_all_active()
    can terminate it immediately on quit, unblocking the worker thread.

    on_proc_started: optional callback invoked with the Popen handle as soon
    as the process is spawned. Lets callers (e.g. a focus dispatcher) cancel
    the subprocess when the user moves on, instead of waiting for it to finish.

    A read timeout (_STREAM_READ_TIMEOUT_S) prevents hangs: if yt-dlp produces
    no output for 30 s, the subprocess is killed and iteration stops.
    """
    from src.platform import IS_WINDOWS, get_popen_kwargs

    logger.debug("yt-dlp cmd: %s", " ".join(cmd))
    try:
        stderr_dest = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_dest,
            text=False,
            bufsize=0,
            **get_popen_kwargs(headless=True),
        )
        with _active_procs_lock:
            _active_procs.add(proc)
        if on_proc_started is not None:
            try:
                on_proc_started(proc)
            except Exception:
                pass
        try:
            if IS_WINDOWS:
                yield from _read_lines_threaded(proc)
            else:
                yield from _read_lines_select(proc)
            proc.wait()
            if capture_stderr and proc.stderr:
                err = proc.stderr.read().decode("utf-8", errors="replace")
                if err.strip():
                    logger.debug("yt-dlp stderr: %s", err.strip())
                if proc.returncode != 0:
                    logger.warning("yt-dlp exited %d: %s", proc.returncode, err.strip())
        finally:
            with _active_procs_lock:
                _active_procs.discard(proc)
    except FileNotFoundError:
        from src.platform import install_hint
        raise RuntimeError(f"yt-dlp not found. Install with: {install_hint('yt-dlp')}")


def _read_lines_select(proc: subprocess.Popen) -> Generator[dict, None, None]:
    """Unix: use select() for timeout-aware reading from stdout pipe."""
    import select
    stdout_fd = proc.stdout.fileno()  # type: ignore[union-attr]
    buf = ""
    while True:
        ready, _, _ = select.select([stdout_fd], [], [], _STREAM_READ_TIMEOUT_S)
        if not ready:
            logger.warning("yt-dlp read timeout (%ds) — killing process", _STREAM_READ_TIMEOUT_S)
            proc.kill()
            break
        raw = os.read(stdout_fd, 65536)
        if not raw:
            break
        buf += raw.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _read_lines_threaded(proc: subprocess.Popen) -> Generator[dict, None, None]:
    """Windows: use a background thread + queue for timeout-aware reading.

    select() on Windows only works with sockets, not pipe file descriptors.
    Instead, we read in a daemon thread and consume with a timeout from a queue.
    """
    import queue
    q: queue.Queue[str | None] = queue.Queue()

    def _reader():
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                q.put(raw_line.decode("utf-8", errors="replace"))
        except (ValueError, OSError):
            pass
        finally:
            q.put(None)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    while True:
        try:
            line = q.get(timeout=_STREAM_READ_TIMEOUT_S)
        except queue.Empty:
            logger.warning("yt-dlp read timeout (%ds) — killing process", _STREAM_READ_TIMEOUT_S)
            proc.kill()
            break
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue



# ── Paged batch fetch ─────────────────────────────────────────────────────────

def fetch_page_batch(
    url: str,
    config,
    cache: Cache,
    *,
    skip_ids: set[str] | None = None,
    count: int = 80,
    feed_key: str | None = None,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> list[dict]:
    """Fetch up to `count` entries from a URL, skipping IDs in skip_ids.

    Used by the paged feed system. Returns a flat list of entry dicts.
    Caches each entry individually. Optionally saves the feed index.

    This is a blocking call meant to run in a background thread.
    """
    if skip_ids is None:
        skip_ids = set()

    # Try cache first if feed_key given
    _MIN_FEED_COUNT = 15
    if feed_key:
        cached_ids = cache.get_feed(feed_key)
        if cached_ids and len(cached_ids) >= _MIN_FEED_COUNT:
            logger.debug("fetch_page_batch cache hit for '%s' (%d ids)", feed_key, len(cached_ids))
            results: list[dict] = []
            for vid_id in cached_ids:
                if vid_id in skip_ids:
                    continue
                if len(results) >= count:
                    break
                entry = cache.get_video_raw(vid_id)
                if entry:
                    results.append(entry)
            if len(results) >= _MIN_FEED_COUNT:
                return results
            logger.debug("fetch_page_batch: only %d cached entries usable, refetching", len(results))

    # Fresh fetch
    logger.debug("fetch_page_batch: fetching %s (count=%d, skip=%d)", url, count, len(skip_ids))
    cmd = ["yt-dlp", *_FAST_FLAGS, *config.cookie_args(), url]
    results: list[dict] = []
    all_ids: list[str] = []

    for entry in _stream_json_lines(
        cmd,
        capture_stderr=logger.is_debug(),
        on_proc_started=on_proc_started,
    ):
        if len(results) >= count:
            break
        if not _is_playable_video(entry):
            continue
        _normalise_entry(entry)
        vid = entry.get("id", "")
        if vid and vid in skip_ids:
            continue
        cache.put_video(entry)
        if vid:
            all_ids.append(vid)
        results.append(entry)

    if feed_key and len(all_ids) >= _MIN_FEED_COUNT:
        cache.put_feed(feed_key, all_ids)
        logger.debug("fetch_page_batch: saved feed '%s' (%d ids)", feed_key, len(all_ids))

    return results


def fetch_search_batch(
    query: str,
    config,
    cache: Cache,
    *,
    skip_ids: set[str] | None = None,
    count: int = 50,
) -> list[dict]:
    """Fetch search results as a batch (for paged search). Returns list of dicts."""
    if skip_ids is None:
        skip_ids = set()

    cache_key = "search_" + hashlib.md5(query.lower().strip().encode()).hexdigest()[:10]
    _MIN_SEARCH_COUNT = 5

    # Cache check
    cached_ids = cache.get_feed(cache_key)
    if cached_ids and len(cached_ids) >= _MIN_SEARCH_COUNT:
        logger.debug("fetch_search_batch cache hit for '%s' (%d ids)", query, len(cached_ids))
        results: list[dict] = []
        for vid_id in cached_ids:
            if vid_id in skip_ids:
                continue
            entry = cache.get_video_raw(vid_id)
            if entry:
                results.append(entry)
        if len(results) >= _MIN_SEARCH_COUNT:
            return results

    # Fresh fetch
    url = f"ytsearch{count}:{query}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--flat-playlist",
        "--extractor-args", "youtube:skip=dash,hls",
        *config.cookie_args(),
        url,
    ]
    results: list[dict] = []
    all_ids: list[str] = []

    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        if not _is_playable_video(entry):
            continue
        _normalise_entry(entry)
        vid = entry.get("id", "")
        if vid and vid in skip_ids:
            continue
        cache.put_video(entry)
        if vid:
            all_ids.append(vid)
        results.append(entry)

    if len(all_ids) >= _MIN_SEARCH_COUNT:
        cache.put_feed(cache_key, all_ids)
    return results


# ── Full metadata (for video detail page) ────────────────────────────────────

def fetch_full(
    video_id: str,
    config,
    cache: Cache,
    *,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> dict | None:
    """Fetch complete metadata for a single video. Returns cached if fresh.

    on_proc_started: optional callback that receives the underlying yt-dlp
    Popen handle. Use this from the caller to support cancellation when the
    user navigates away before the fetch completes.
    """
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
        *config.cookie_args(),
        url,
    ]
    logger.debug("fetch_full fetching: %s", video_id)
    results = list(_stream_json_lines(
        cmd,
        capture_stderr=logger.is_debug(),
        on_proc_started=on_proc_started,
    ))
    if not results:
        logger.warning("fetch_full got no data for %s — falling back to flat cache", video_id)
        return cache.get_video_raw(video_id)
    entry = results[0]
    _normalise_entry(entry)
    cache.put_video(entry)
    return entry


# ── Stream URL prefetch ───────────────────────────────────────────────────────

def fetch_stream_urls(
    video_id: str,
    config,
    *,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> dict | None:
    """Fetch direct stream URLs for best audio and best video formats.

    Returns a dict with keys: audio_url, video_url, expire, fetched_at.
    Returns None on failure. Does NOT use the skip=dash,hls flag so that
    yt-dlp resolves actual streaming URLs.
    """
    import time

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--skip-download",
        *config.cookie_args(),
        url,
    ]
    logger.debug("fetch_stream_urls: %s", video_id)
    results = list(_stream_json_lines(
        cmd,
        capture_stderr=logger.is_debug(),
        on_proc_started=on_proc_started,
    ))
    if not results:
        logger.warning("fetch_stream_urls got no data for %s", video_id)
        return None

    info = results[0]
    formats = info.get("formats") or []
    if not formats:
        logger.debug("fetch_stream_urls: no formats in response for %s", video_id)
        return None

    best_audio_url = _pick_best_audio_url(formats)
    best_video_url = _pick_best_video_url(formats)

    if not best_audio_url and not best_video_url:
        return None

    expire = _extract_expire(best_audio_url or best_video_url or "")

    return {
        "audio_url": best_audio_url,
        "video_url": best_video_url,
        "expire": expire,
        "fetched_at": time.time(),
    }


def _pick_best_audio_url(formats: list[dict]) -> str | None:
    """Select the best audio-only format URL from yt-dlp formats list."""
    audio_formats = [
        f for f in formats
        if f.get("acodec", "none") != "none"
        and f.get("vcodec", "none") in ("none", None)
        and f.get("url")
    ]
    if not audio_formats:
        return None
    audio_formats.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
    return audio_formats[0]["url"]


def _pick_best_video_url(formats: list[dict]) -> str | None:
    """Select the best video-only format URL from yt-dlp formats list."""
    video_formats = [
        f for f in formats
        if f.get("vcodec", "none") != "none"
        and f.get("acodec", "none") in ("none", None)
        and f.get("url")
    ]
    if not video_formats:
        return None
    video_formats.sort(
        key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True
    )
    return video_formats[0]["url"]


def _extract_expire(url: str) -> int:
    """Extract the expire= query parameter from a YouTube stream URL."""
    from urllib.parse import urlparse, parse_qs
    try:
        parsed = urlparse(url)
        expire_vals = parse_qs(parsed.query).get("expire", [])
        if expire_vals:
            return int(expire_vals[0])
    except (ValueError, TypeError):
        pass
    return 0


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
_DESTINATION_RE = re.compile(r'\[download\] Destination:')
_POSTPROCESS_RE = re.compile(
    r'\[(Merger|ExtractAudio|FFmpegVideoConvertor|FFmpegExtractAudio|FFmpegMetadata)\]'
)

# Phase constants emitted via pct parameter
PHASE_NEW_STREAM = -2.0
PHASE_POSTPROCESS = -3.0


def _run_download_with_progress(
    cmd: list[str],
    on_progress: Callable[[str, float], None] | None = None,
) -> bool:
    """Run a yt-dlp download command, streaming progress. Returns True on success."""
    from src.platform import get_popen_kwargs
    logger.debug("download cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
            **get_popen_kwargs(headless=True),
        )
        with _active_procs_lock:
            _active_procs.add(proc)
        try:
            stream_count = 0
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip()
                if _DESTINATION_RE.search(line):
                    stream_count += 1
                    if on_progress and stream_count > 1:
                        on_progress(line, PHASE_NEW_STREAM)
                    continue
                if _POSTPROCESS_RE.search(line):
                    if on_progress:
                        on_progress(line, PHASE_POSTPROCESS)
                    continue
                m = _PROGRESS_RE.search(line)
                pct = float(m.group(1)) if m else -1.0
                if on_progress:
                    on_progress(line, pct)
                elif pct >= 0:
                    filled = int(pct / 2)
                    bar = "█" * filled + "░" * (50 - filled)
                    sys.stderr.write(f"\r  [{bar}] {pct:5.1f}%")
                    sys.stderr.flush()
            if on_progress is None:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
            proc.wait()
            return proc.returncode == 0
        finally:
            with _active_procs_lock:
                _active_procs.discard(proc)
    except FileNotFoundError:
        from src.platform import install_hint
        raise RuntimeError(f"yt-dlp not found. Install with: {install_hint('yt-dlp')}")


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
        *config.cookie_args(),
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
        *config.cookie_args(),
        url,
    ]
    return _run_download_with_progress(cmd, on_progress)



# -- Channel browsing --------------------------------------------------------

# Strips known tab suffixes from a channel URL so we can append the desired
# one cleanly — avoids double-suffixing like /videos/videos.
_CH_SUFFIX_RE = re.compile(
    r"/(videos|shorts|streams|playlists|community|about|featured|membership|store)(/.*)?$",
    re.IGNORECASE,
)


def _normalise_channel_url(url: str) -> str:
    """Strip any existing channel-tab path component from a YouTube channel URL."""
    return _CH_SUFFIX_RE.sub("", url.rstrip("/"))


def fetch_channel_info(
    channel_url: str,
    config,
    cache: Cache,
    *,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> dict | None:
    """Fetch basic channel metadata (name, description, subscriber count)."""
    cache_key = "ch:info:" + hashlib.md5(channel_url.encode()).hexdigest()[:12]
    cached = cache.get_video(cache_key)
    if cached:
        return cached
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-items", "0",
        "--no-warnings",
        *config.cookie_args(),
        channel_url,
    ]
    try:
        from src.platform import get_popen_kwargs
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", **get_popen_kwargs(headless=True),
        )
        with _active_procs_lock: _active_procs.add(proc)
        if on_proc_started: on_proc_started(proc)
        try:
            stdout, _ = proc.communicate(timeout=30)
        finally:
            with _active_procs_lock: _active_procs.discard(proc)
        if proc.returncode != 0 or not stdout.strip():
            return None
        data = json.loads(stdout)
        thumbs = data.get("thumbnails") or []
        avatar_url = ""
        for t in reversed(thumbs):
            if t.get("id") == "avatar_uncropped":
                avatar_url = t.get("url", "")
                break
        if not avatar_url:
            avatar_url = thumbs[-1].get("url", "") if thumbs else data.get("thumbnail", "")

        info = {
            "_cache_key": cache_key,
            "channel_url": channel_url,
            "channel": data.get("channel") or data.get("uploader") or data.get("title", ""),
            "channel_id": data.get("channel_id") or data.get("uploader_id", ""),
            "description": data.get("description", ""),
            "subscriber_count": data.get("channel_follower_count"),
            "thumbnail": avatar_url,
            "uploader_url": data.get("uploader_url", ""),
        }
        cache.put_video(info)
        return info
    except Exception as exc:
        logger.debug("fetch_channel_info error: %s", exc)
        return None


def fetch_channel_videos(
    channel_url: str,
    config,
    cache: Cache,
    *,
    sort: str = "date",
    count: int = 80,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> list[dict]:
    """Fetch video entries from a channel. sort: date | views."""
    base_url = _normalise_channel_url(channel_url)
    if sort == "views":
        url = base_url + "/videos?sort=p"
    else:
        url = base_url + "/videos"
    logger.debug("fetch_channel_videos: url=%s sort=%s", url, sort)
    return fetch_page_batch(url, config, cache, count=count, on_proc_started=on_proc_started)


def fetch_channel_playlists(
    channel_url: str,
    config,
    cache: Cache,
    *,
    count: int = 80,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> list[dict]:
    """Fetch playlist entries from a channel."""
    url = _normalise_channel_url(channel_url) + "/playlists"
    logger.debug("fetch_channel_playlists: url=%s", url)
    cmd = ["yt-dlp", *_FAST_FLAGS, *config.cookie_args(), url]
    results: list[dict] = []
    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug(), on_proc_started=on_proc_started):
        if len(results) >= count:
            break
        etype = entry.get("_type", "")
        if etype not in ("playlist", "url") and not entry.get("id"):
            continue
        _normalise_entry(entry)
        pid = entry.get("id", "")
        if pid:
            entry.setdefault("_is_playlist", True)
            entry.setdefault("_playlist_name", entry.get("title", pid))
        results.append(entry)
    return results


def fetch_subscribed_channels(config, cache: Cache, *, on_proc_started=None) -> list[dict]:
    """Fetch subscribed channels."""
    url = "https://www.youtube.com/feed/channels"
    cache_key = "subs:channels"
    cached = cache.get_feed(cache_key)
    if cached:
        entries = [e for cid in cached for e in [cache.get_video_raw(cid)] if e]
        if entries:
            for e in entries: e["_is_channel"] = True
            return entries
    flat = "--flat-playlist"
    cmd = ["yt-dlp", flat, "--dump-json", "--no-warnings", "--quiet",
           *config.cookie_args(), url]
    results: list[dict] = []
    seen: list[str] = []
    try:
        from src.platform import get_popen_kwargs
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", **get_popen_kwargs(headless=True))
        with _active_procs_lock: _active_procs.add(proc)
        if on_proc_started: on_proc_started(proc)
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                cid = data.get("id") or data.get("channel_id") or ""
                if not cid: continue
                name = data.get("title") or data.get("channel") or data.get("uploader") or cid
                ch_url = data.get("url") or data.get("channel_url") or ""
                subs = data.get("channel_follower_count")
                vcnt = data.get("playlist_count")
                entry = {"id": cid, "title": name, "channel": name, "channel_url": ch_url, "channel_id": cid, "uploader": name, "uploader_url": ch_url, "subscriber_count": subs, "video_count": vcnt, "thumbnail": data.get("thumbnail") or "", "description": data.get("description") or "", "_is_channel": True}
                cache.put_video(entry)
                results.append(entry)
                seen.append(cid)
        finally:
            with _active_procs_lock: _active_procs.discard(proc)
    except Exception as exc:
        logger.debug("subs ch exc: %s", exc)
    if seen: cache.put_feed(cache_key, seen)
    return results
