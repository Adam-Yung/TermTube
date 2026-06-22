"""yt-dlp interface — direct Python library integration (no subprocess).

Progressive streaming design:
  fetch_page_batch()   →  cache-first paged fetch: uses extract_info with
                          lazy_playlist for incremental entry retrieval.
  fetch_search_batch() →  same, keyed by query hash.
"""

from __future__ import annotations
import hashlib
import re
import threading
from typing import Callable

import yt_dlp

from src.cache import Cache
from src import logger


# ── Shared options builder ────────────────────────────────────────────────────

def _base_opts(config) -> dict:
    """Build base YoutubeDL options from app config."""
    from src.bootstrap import get_deps_bin
    import sys

    deno_name = "deno.exe" if sys.platform == "win32" else "deno"
    deno_path = get_deps_bin() / deno_name

    opts: dict = {
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
        'socket_timeout': 30,
    }
    if deno_path.exists():
        opts['js_runtimes'] = {'deno': {'path': str(deno_path)}}
    cf = config.cookies_file
    if cf:
        opts['cookiefile'] = str(cf)
    return opts


# ── Cancellation infrastructure ───────────────────────────────────────────────

_cancel_events: set[threading.Event] = set()
_cancel_lock = threading.Lock()


def _new_cancel_event() -> threading.Event:
    ev = threading.Event()
    with _cancel_lock:
        _cancel_events.add(ev)
    return ev


def _release_cancel_event(ev: threading.Event) -> None:
    with _cancel_lock:
        _cancel_events.discard(ev)


def cancel_all() -> None:
    """Signal all active yt-dlp operations to stop.

    Called by the TUI before exit so that worker threads blocked on
    yt-dlp network I/O unblock immediately, preventing the app from hanging.
    """
    with _cancel_lock:
        for ev in _cancel_events:
            ev.set()
        _cancel_events.clear()


# ── Feed URLs ─────────────────────────────────────────────────────────────────

_MAX_RETRIES = 1
_RETRY_DELAY_S = 2.0

FEED_URLS = {
    "home":          "https://www.youtube.com/feed/recommended",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}

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
    """Return True only for proper YouTube video entries."""
    vid = entry.get("id", "")
    if not _VIDEO_ID_RE.match(vid):
        return False
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


# ── Paged batch fetch ─────────────────────────────────────────────────────────

def fetch_page_batch(
    url: str,
    config,
    cache: Cache,
    *,
    skip_ids: set[str] | None = None,
    count: int = 80,
    feed_key: str | None = None,
) -> list[dict]:
    """Fetch up to `count` entries from a URL, skipping IDs in skip_ids.

    Used by the paged feed system. Returns a flat list of entry dicts.
    Caches each entry individually. Optionally saves the feed index.
    This is a blocking call meant to run in a background thread.
    """
    if skip_ids is None:
        skip_ids = set()

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

    logger.debug("fetch_page_batch: fetching %s (count=%d, skip=%d)", url, count, len(skip_ids))

    opts = _base_opts(config)
    opts['extract_flat'] = 'in_playlist'
    opts['lazy_playlist'] = True

    results: list[dict] = []
    all_ids: list[str] = []

    cancel = _new_cancel_event()
    try:
        for attempt in range(_MAX_RETRIES + 1):
            results = []
            all_ids = []
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        break
                    for entry in (info.get('entries') or []):
                        if cancel.is_set():
                            break
                        if len(results) >= count:
                            break
                        if entry is None:
                            continue
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
            except yt_dlp.utils.DownloadError as exc:
                logger.debug("fetch_page_batch error: %s", exc)

            if results or attempt >= _MAX_RETRIES:
                break
            logger.debug("fetch_page_batch: empty result, retrying (%d/%d)", attempt + 1, _MAX_RETRIES)
            import time
            time.sleep(_RETRY_DELAY_S)
    finally:
        _release_cancel_event(cancel)

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

    url = f"ytsearch{count}:{query}"
    opts = _base_opts(config)
    opts['extract_flat'] = 'in_playlist'
    opts['lazy_playlist'] = True

    results: list[dict] = []
    all_ids: list[str] = []

    cancel = _new_cancel_event()
    try:
        for attempt in range(_MAX_RETRIES + 1):
            results = []
            all_ids = []
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        break
                    for entry in (info.get('entries') or []):
                        if cancel.is_set():
                            break
                        if entry is None:
                            continue
                        if not _is_playable_video(entry):
                            continue
                        _normalise_entry(entry)
                        vid = entry.get("id", "")
                        if vid and skip_ids and vid in skip_ids:
                            continue
                        cache.put_video(entry)
                        if vid:
                            all_ids.append(vid)
                        results.append(entry)
            except yt_dlp.utils.DownloadError as exc:
                logger.debug("fetch_search_batch error: %s", exc)

            if results or attempt >= _MAX_RETRIES:
                break
            logger.debug("fetch_search_batch: empty result, retrying (%d/%d)", attempt + 1, _MAX_RETRIES)
            import time
            time.sleep(_RETRY_DELAY_S)
    finally:
        _release_cancel_event(cancel)

    if len(all_ids) >= _MIN_SEARCH_COUNT:
        cache.put_feed(cache_key, all_ids)
    return results


# ── Download ──────────────────────────────────────────────────────────────────

# Quality helpers (public constants used by UI modals)
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

PHASE_NEW_STREAM = -2.0
PHASE_POSTPROCESS = -3.0


def _make_progress_hook(on_progress: Callable[[str, float], None] | None, cancel: threading.Event):
    """Create a yt-dlp progress hook bridging to the app's UI callback."""
    def hook(d: dict) -> None:
        if cancel.is_set():
            raise yt_dlp.utils.DownloadError("Cancelled by user")
        if on_progress is None:
            return
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                pct = downloaded / total * 100.0
            else:
                pct = -1.0
            on_progress(d.get('_default_template', ''), pct)
        elif status == 'finished':
            on_progress("Post-processing...", PHASE_POSTPROCESS)
    return hook


def _make_postprocessor_hook(on_progress: Callable[[str, float], None] | None):
    """Create a yt-dlp postprocessor hook for merge/extraction progress."""
    def hook(d: dict) -> None:
        if on_progress is None:
            return
        status = d.get('status')
        if status == 'started':
            on_progress(f"[{d.get('postprocessor', 'PP')}] Processing...", PHASE_POSTPROCESS)
    return hook


def _quality_to_format(quality: str) -> str:
    """Convert a config quality value (e.g. 'best', '1080') to a format string."""
    if quality == "best":
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={quality}]+bestaudio/best"


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
        fmt = _quality_to_format(config.preferred_quality)

    logger.info("download_video %s (format=%s)", video_id, fmt)

    opts = _base_opts(config)
    opts['format'] = fmt
    opts['merge_output_format'] = 'mp4'
    opts['outtmpl'] = str(config.video_dir / config.video_format)
    opts['writeinfojson'] = True
    opts['writethumbnail'] = True
    opts['noprogress'] = True

    cancel = _new_cancel_event()
    opts['progress_hooks'] = [_make_progress_hook(on_progress, cancel)]
    opts['postprocessor_hooks'] = [_make_postprocessor_hook(on_progress)]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.download([url]) == 0
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("download_video error: %s", exc)
        return False
    finally:
        _release_cancel_event(cancel)


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

    opts = _base_opts(config)
    opts['format'] = 'bestaudio/best'
    opts['outtmpl'] = str(config.audio_dir / config.audio_format)
    opts['postprocessors'] = [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '0',
    }]
    opts['writeinfojson'] = True
    opts['writethumbnail'] = True
    opts['noprogress'] = True

    cancel = _new_cancel_event()
    opts['progress_hooks'] = [_make_progress_hook(on_progress, cancel)]
    opts['postprocessor_hooks'] = [_make_postprocessor_hook(on_progress)]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.download([url]) == 0
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("download_audio error: %s", exc)
        return False
    finally:
        _release_cancel_event(cancel)


# ── Channel browsing ──────────────────────────────────────────────────────────

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
) -> dict | None:
    """Fetch basic channel metadata (name, description, subscriber count)."""
    cache_key = "ch:info:" + hashlib.md5(channel_url.encode()).hexdigest()[:12]
    cached = cache.get_video(cache_key)
    if cached:
        return cached

    opts = _base_opts(config)
    opts['extract_flat'] = 'in_playlist'
    opts['playlist_items'] = '0'

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(channel_url, download=False)
        if not data:
            return None

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
) -> list[dict]:
    """Fetch video entries from a channel. sort: date | views."""
    base_url = _normalise_channel_url(channel_url)
    if sort == "views":
        url = base_url + "/videos?sort=p"
    else:
        url = base_url + "/videos"
    logger.debug("fetch_channel_videos: url=%s sort=%s", url, sort)
    return fetch_page_batch(url, config, cache, count=count)


def fetch_channel_playlists(
    channel_url: str,
    config,
    cache: Cache,
    *,
    count: int = 80,
) -> list[dict]:
    """Fetch playlist entries from a channel."""
    url = _normalise_channel_url(channel_url) + "/playlists"
    logger.debug("fetch_channel_playlists: url=%s", url)

    opts = _base_opts(config)
    opts['extract_flat'] = 'in_playlist'
    opts['lazy_playlist'] = True

    results: list[dict] = []
    cancel = _new_cancel_event()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return results
            for entry in (info.get('entries') or []):
                if cancel.is_set():
                    break
                if len(results) >= count:
                    break
                if entry is None:
                    continue
                etype = entry.get("_type", "")
                if etype not in ("playlist", "url") and not entry.get("id"):
                    continue
                _normalise_entry(entry)
                pid = entry.get("id", "")
                if pid:
                    entry.setdefault("_is_playlist", True)
                    entry.setdefault("_playlist_name", entry.get("title", pid))
                results.append(entry)
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("fetch_channel_playlists error: %s", exc)
    finally:
        _release_cancel_event(cancel)
    return results


def fetch_subscribed_channels(config, cache: Cache) -> list[dict]:
    """Fetch subscribed channels (with 60s timeout)."""
    url = "https://www.youtube.com/feed/channels"
    cache_key = "subs:channels"
    cached = cache.get_feed(cache_key)
    if cached:
        entries = [e for cid in cached for e in [cache.get_video_raw(cid)] if e]
        if entries:
            for e in entries:
                e["_is_channel"] = True
            return entries

    opts = _base_opts(config)
    opts['extract_flat'] = 'in_playlist'
    opts['lazy_playlist'] = True
    opts['socket_timeout'] = 60

    results: list[dict] = []
    seen: list[str] = []
    cancel = _new_cancel_event()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return results
            for data in (info.get('entries') or []):
                if cancel.is_set():
                    break
                if data is None:
                    continue
                cid = data.get("id") or data.get("channel_id") or ""
                if not cid:
                    continue
                name = data.get("title") or data.get("channel") or data.get("uploader") or cid
                ch_url = data.get("url") or data.get("channel_url") or ""
                subs = data.get("channel_follower_count")
                vcnt = data.get("playlist_count")
                entry = {
                    "id": cid, "title": name, "channel": name,
                    "channel_url": ch_url, "channel_id": cid,
                    "uploader": name, "uploader_url": ch_url,
                    "subscriber_count": subs, "video_count": vcnt,
                    "thumbnail": data.get("thumbnail") or "",
                    "description": data.get("description") or "",
                    "_is_channel": True,
                }
                cache.put_video(entry)
                results.append(entry)
                seen.append(cid)
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("fetch_subscribed_channels error: %s", exc)
    finally:
        _release_cancel_event(cancel)

    if seen:
        cache.put_feed(cache_key, seen)
    return results


# ── Stream URL pre-resolution ─────────────────────────────────────────────────

def resolve_stream_url(
    video_id: str,
    config,
    format_spec: str = "ba[format_note*=original]/ba",
) -> list[str] | None:
    """Resolve a YouTube video ID to direct playable stream URL(s).

    Returns a list of URLs (may be 1 for audio-only, or 2 for video+audio)
    or None on failure.
    """
    opts = _base_opts(config)
    opts['format'] = format_spec

    logger.debug("resolve_stream_url: video_id=%s format=%s", video_id, format_spec)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            if not info:
                return None
            if info.get('requested_formats'):
                return [f['url'] for f in info['requested_formats']]
            if info.get('url'):
                return [info['url']]
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("resolve_stream_url failed: %s", exc)
    except Exception as exc:
        logger.debug("resolve_stream_url exception: %s", exc)
    return None
