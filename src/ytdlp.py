"""TermTube v2 — yt-dlp wrapper.

Uses the yt-dlp Python API (yt_dlp.YoutubeDL) for all metadata operations.
Subprocesses are used only for actual downloads where --newline progress
parsing is simpler than hooking the Python API download loop.

Cancellation pattern
--------------------
Any long-running extract_info call accepts a `cancel_event: threading.Event`.
A progress_hook is registered that raises yt_dlp.utils.DownloadCancelled
when the event is set.  Callers set the event from any thread; yt-dlp
raises on the next progress tick (at most a few hundred ms later).

Threading
---------
All public functions MUST be called from a worker thread, never from the
Textual main thread.  They are synchronous and may block for several seconds.
"""
from __future__ import annotations

import hashlib
import subprocess
import threading
import time
from typing import Any, Callable, Iterator

import yt_dlp
import yt_dlp.utils

import cache as _cache
from config import Config
import logger

# Feed URLs
FEED_URLS: dict[str, str] = {
    "home": "https://www.youtube.com/feed/recommended",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}

QUALITY_CHOICES = [
    ("Best available",         "bestvideo+bestaudio/best"),
    ("1080p",                  "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("720p",                   "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("480p",                   "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("360p",                   "bestvideo[height<=360]+bestaudio/best[height<=360]"),
    ("Audio only (best)",      "bestaudio/best"),
]

AUDIO_QUALITY_CHOICES = [
    ("Best audio",   "bestaudio/best"),
    ("Medium audio", "bestaudio[abr<=128]/best"),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base_opts(config: Config) -> dict[str, Any]:
    """Base yt-dlp options shared by all calls."""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        **config.ydl_cookie_opts,
    }
    return opts


def _cancel_hook(cancel_event: threading.Event) -> Callable[[dict], None]:
    """Return a progress_hook that raises DownloadCancelled when event is set."""
    def hook(d: dict) -> None:
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled()
    return hook


def _search_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Paged feed / search
# ---------------------------------------------------------------------------

def fetch_page(
    source: str,
    page: int,
    config: Config,
    *,
    page_size: int | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[list[dict], bool]:
    """Fetch one page of results.

    source: a FEED_URLS key ("home", "subscriptions"), a search query string,
            or a channel URL.
    page:   1-based page number.
    Returns (entries, has_more).
    Checks cache first; fetches from network only on cache miss or stale.
    """
    ps = page_size or config.page_size
    ttl = config.ttl("search") if source not in FEED_URLS else config.ttl("home")

    if source in FEED_URLS:
        feed_key = source
    else:
        feed_key = f"search_{_search_key(source)}"

    cached = _cache.get_page(feed_key, page, ttl)
    if cached is not None:
        logger.debug("cache hit page %s/%d", feed_key, page)
        has_more = _cache.get_page_stale(feed_key, page + 1) is not None or True
        return cached, has_more

    logger.debug("fetching page %s/%d from network", feed_key, page)

    if source in FEED_URLS:
        url = FEED_URLS[source]
        opts = {
            **_base_opts(config),
            "extract_flat": "in_playlist",
            "playliststart": (page - 1) * ps + 1,
            "playlistend": page * ps,
        }
    else:
        start = (page - 1) * ps + 1
        url = f"ytsearch{page * ps}:{source}"
        opts = {
            **_base_opts(config),
            "extract_flat": True,
            "playliststart": start,
            "playlistend": page * ps,
        }

    if cancel_event:
        opts["progress_hooks"] = [_cancel_hook(cancel_event)]

    entries: list[dict] = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if result and "entries" in result:
                raw = [e for e in result["entries"] if e]
                for e in raw:
                    _cache.put_video(e)
                entries = raw
    except yt_dlp.utils.DownloadCancelled:
        logger.debug("fetch_page cancelled: %s/%d", feed_key, page)
        return [], False
    except Exception as exc:
        logger.warning("fetch_page error: %s", exc)
        stale = _cache.get_page_stale(feed_key, page)
        return stale or [], False

    if entries:
        _cache.put_page(feed_key, page, entries)

    has_more = len(entries) >= ps
    return entries, has_more


def stream_home(
    config: Config,
    *,
    on_entry: Callable[[dict], None],
    cancel_event: threading.Event | None = None,
    max_count: int = 100,
) -> None:
    """Stream home/subscriptions feed entries one-by-one via on_entry callback.

    Used for the home feed where streaming feels more responsive than waiting
    for a full page. The caller still writes to the paged cache.
    """
    url = FEED_URLS["home"]
    opts = {
        **_base_opts(config),
        "extract_flat": "in_playlist",
        "playlistend": max_count,
    }

    count = 0
    entries: list[dict] = []

    def _hook(d: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled()

    opts["progress_hooks"] = [_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if result and "entries" in result:
                for e in result["entries"]:
                    if not e:
                        continue
                    if cancel_event and cancel_event.is_set():
                        break
                    _cache.put_video(e)
                    entries.append(e)
                    on_entry(e)
                    count += 1
                    if count >= max_count:
                        break
    except yt_dlp.utils.DownloadCancelled:
        logger.debug("stream_home cancelled after %d entries", count)
    except Exception as exc:
        logger.warning("stream_home error: %s", exc)

    # Cache page 1 from what we got
    ps = config.page_size
    if entries:
        pages = [entries[i:i + ps] for i in range(0, len(entries), ps)]
        for i, pg in enumerate(pages, start=1):
            _cache.put_page("home", i, pg)


# ---------------------------------------------------------------------------
# Full metadata fetch (focus worker)
# ---------------------------------------------------------------------------

def fetch_full(
    video_id: str,
    config: Config,
    *,
    cancel_event: threading.Event | None = None,
) -> dict | None:
    """Fetch complete metadata for a single video.

    Checks cache first (returns immediately on hit with description present).
    On cache miss, fetches via yt-dlp Python API.
    """
    cached = _cache.get_video(video_id, ttl=config.ttl("metadata"))
    if cached and cached.get("description") is not None:
        logger.debug("cache hit metadata %s", video_id)
        return cached

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        **_base_opts(config),
        "skip_download": True,
    }
    if cancel_event:
        opts["progress_hooks"] = [_cancel_hook(cancel_event)]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            entry = ydl.extract_info(url, download=False)
        if entry:
            _cache.put_video(entry)
            return entry
    except yt_dlp.utils.DownloadCancelled:
        logger.debug("fetch_full cancelled: %s", video_id)
    except Exception as exc:
        logger.warning("fetch_full error %s: %s", video_id, exc)
        return _cache.get_video_raw(video_id)

    return None


# ---------------------------------------------------------------------------
# Downloads (subprocess — progress line parsing)
# ---------------------------------------------------------------------------

def download_video(
    video_id: str,
    config: Config,
    *,
    quality_format: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> bool:
    """Download video to config.video_dir.  Returns True on success."""
    fmt = quality_format or config.preferred_quality
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_dir = config.video_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-thumbnail",
        "--newline",
        "--output", str(out_dir / config.video_format),
        *config.cookie_args,
        url,
    ]

    return _run_download(cmd, on_progress)


def download_audio(
    video_id: str,
    config: Config,
    *,
    quality_format: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> bool:
    """Download audio to config.audio_dir.  Returns True on success."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_dir = config.audio_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--write-info-json",
        "--write-thumbnail",
        "--newline",
        "--output", str(out_dir / config.audio_format),
        *config.cookie_args,
        url,
    ]

    return _run_download(cmd, on_progress)


def _run_download(
    cmd: list[str],
    on_progress: Callable[[dict], None] | None,
) -> bool:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            if on_progress:
                d = _parse_progress_line(line)
                if d:
                    on_progress(d)
        proc.wait()
        return proc.returncode == 0
    except Exception as exc:
        logger.warning("download error: %s", exc)
        return False


def _parse_progress_line(line: str) -> dict | None:
    """Parse yt-dlp --newline progress into a dict."""
    if "[download]" not in line:
        return None
    d: dict[str, Any] = {"raw": line}
    import re
    pct = re.search(r"(\d+\.?\d*)%", line)
    if pct:
        d["percent"] = float(pct.group(1))
    speed = re.search(r"at\s+([\d.]+\s*\w+/s)", line)
    if speed:
        d["speed"] = speed.group(1)
    eta = re.search(r"ETA\s+([\d:]+)", line)
    if eta:
        d["eta"] = eta.group(1)
    return d


# ---------------------------------------------------------------------------
# Thumbnail download
# ---------------------------------------------------------------------------

def download_thumb(video_id: str, url: str) -> bool:
    """Download thumbnail JPEG to cache.  Returns True on success."""
    import urllib.request
    dest = _cache.thumb_path(video_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = resp.read()
        dest.write_bytes(data)
        return True
    except Exception as exc:
        logger.debug("thumb download failed %s: %s", video_id, exc)
        return False
