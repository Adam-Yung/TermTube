from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

import yt_dlp

from src import logger
from src.local_files import is_local_id
from src.ytdlp import base_opts, new_cancel_event, release_cancel_event

_STREAM_URL_TTL = 3600 * 5  # YouTube CDN URLs expire after about 6 hours
_STREAM_CACHE_MAX = 40
_EVENTS_MAX = 25
_STREAM_URL_WARMUP_MAX = 1.5
_PREFETCH_WAIT_S = 2.0

_stream_cache: dict[str, tuple[float, list[str]]] = {}
_stream_cache_lock = threading.Lock()
_prefetch_events: dict[str, threading.Event] = {}
_prefetch_events_lock = threading.Lock()
_cdn_ready_events: dict[str, threading.Event] = {}
_cdn_ready_lock = threading.Lock()


def _key(video_id: str, format_spec: str) -> str:
    return f"{video_id}:{format_spec}"


def resolve_stream_url(
    video_id: str,
    config,
    format_spec: str = "ba/b",
    cancel_event: threading.Event | None = None,
) -> list[str] | None:
    """Resolve a video ID to direct stream URL(s): one for audio, two (video, audio) for merged formats.

    Returns None on failure or cancellation. Never uses cookies (see docs/code/src/ytdlp.py.md).
    """
    if is_local_id(video_id):
        return None
    cancel = cancel_event or new_cancel_event()
    opts = base_opts(skip_manifests=False)
    opts['format'] = format_spec

    logger.debug("resolve_stream_url: video_id=%s format=%s", video_id, format_spec)
    try:
        if cancel.is_set():
            return None
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if cancel.is_set() or not info:
                return None
            if info.get('requested_formats'):
                return [f['url'] for f in info['requested_formats']]
            if info.get('url'):
                return [info['url']]
    except Exception as exc:
        logger.debug("resolve_stream_url failed: %s", exc)
    finally:
        if cancel_event is None:
            release_cancel_event(cancel)
    return None


def get_cached_stream_url(video_id: str, format_spec: str) -> list[str] | None:
    """Return pre-resolved stream URLs if cached and fresh, else None."""
    key = _key(video_id, format_spec)
    with _stream_cache_lock:
        entry = _stream_cache.get(key)
        if entry is None:
            return None
        ts, urls = entry
        if time.time() - ts > _STREAM_URL_TTL:
            del _stream_cache[key]
            return None
        return urls


def put_cached_stream_url(video_id: str, format_spec: str, urls: list[str]) -> None:
    """Cache resolved stream URLs and start the CDN readiness probe."""
    with _stream_cache_lock:
        _stream_cache[_key(video_id, format_spec)] = (time.time(), urls)
        if len(_stream_cache) > _STREAM_CACHE_MAX:
            oldest_key = min(_stream_cache, key=lambda k: _stream_cache[k][0])
            del _stream_cache[oldest_key]
    _start_cdn_probe(video_id, format_spec, urls)


def invalidate_cached_stream_url(video_id: str, format_spec: str) -> None:
    with _stream_cache_lock:
        _stream_cache.pop(_key(video_id, format_spec), None)


def wait_for_prefetch(video_id: str, format_spec: str, timeout: float = 2.0) -> list[str] | None:
    """Cached URLs, waiting up to ``timeout`` s for an in-flight prefetch. None if none started or it timed out."""
    cached = get_cached_stream_url(video_id, format_spec)
    if cached:
        return cached
    with _prefetch_events_lock:
        ev = _prefetch_events.get(_key(video_id, format_spec))
    if ev is None:
        return None
    ev.wait(timeout=timeout)
    return get_cached_stream_url(video_id, format_spec)


def _probe_cdn_ready(url: str, key: str) -> None:
    """Range-GET the CDN until it answers (3 tries), then signal readiness either way."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Range", "bytes=0-0")

    for _ in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=2)
            resp.read()
            resp.close()
            break
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            time.sleep(0.5)
    with _cdn_ready_lock:
        ev = _cdn_ready_events.get(key)
    if ev:
        ev.set()


def _start_cdn_probe(video_id: str, format_spec: str, urls: list[str]) -> None:
    key = _key(video_id, format_spec)
    ev = threading.Event()
    with _cdn_ready_lock:
        _cdn_ready_events[key] = ev
        if len(_cdn_ready_events) > _EVENTS_MAX:
            del _cdn_ready_events[next(iter(_cdn_ready_events))]
    threading.Thread(target=_probe_cdn_ready, args=(urls[0], key), daemon=True).start()


def wait_for_stream_url_ready(video_id: str, format_spec: str) -> None:
    """Block until the CDN probe finishes or ``_STREAM_URL_WARMUP_MAX`` s pass."""
    key = _key(video_id, format_spec)
    with _cdn_ready_lock:
        ev = _cdn_ready_events.get(key)
    if ev is None:
        # No probe yet (URL resolved inline). The CDN is likely warm from the extraction
        # handshake, so only probe if the URL is younger than the warmup window.
        with _stream_cache_lock:
            entry = _stream_cache.get(key)
            if entry is None:
                return
            resolve_ts, urls = entry
        if time.time() - resolve_ts >= _STREAM_URL_WARMUP_MAX:
            return
        _start_cdn_probe(video_id, format_spec, urls)
        with _cdn_ready_lock:
            ev = _cdn_ready_events.get(key)
        if ev is None:
            return
    ev.wait(timeout=_STREAM_URL_WARMUP_MAX)


def prefetch_stream_url(video_id: str, config, format_spec: str = "ba/b") -> None:
    """Resolve and cache a stream URL in the background; no-op if already cached.

    Sets a per-key event on completion so ``wait_for_prefetch`` wakes without polling.
    """
    if get_cached_stream_url(video_id, format_spec) is not None:
        return

    ev = threading.Event()
    with _prefetch_events_lock:
        _prefetch_events[_key(video_id, format_spec)] = ev
        if len(_prefetch_events) > _EVENTS_MAX:
            del _prefetch_events[next(iter(_prefetch_events))]
    try:
        urls = resolve_stream_url(video_id, config, format_spec=format_spec)
        if urls:
            put_cached_stream_url(video_id, format_spec, urls)
            logger.debug("prefetch_stream_url: cached %d URL(s) for %s", len(urls), video_id)
    finally:
        ev.set()


def _resolve_and_cache(video_id: str, config, format_spec: str) -> list[str] | None:
    urls = resolve_stream_url(video_id, config, format_spec=format_spec)
    if urls:
        put_cached_stream_url(video_id, format_spec, urls)
        wait_for_stream_url_ready(video_id, format_spec)
    return urls


def resolve_for_playback(
    video_id: str,
    config,
    format_spec: str,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    on_resolving: Callable[[], None] | None = None,
) -> tuple[list[str] | None, bool]:
    """Stream URLs to play now, and whether they came from the cache.

    Order: the URL cache, a prefetch already in flight, then a fresh resolve. A freshly
    resolved URL is held until the CDN answers a probe, so mpv does not open it early.
    """
    urls = get_cached_stream_url(video_id, format_spec) or wait_for_prefetch(
        video_id, format_spec, timeout=_PREFETCH_WAIT_S
    )
    if urls:
        return urls, True
    if cancelled():
        return None, False
    if on_resolving:
        on_resolving()
    return _resolve_and_cache(video_id, config, format_spec), False


def re_resolve(video_id: str, config, format_spec: str) -> list[str] | None:
    """Drop the cached URL and resolve again, after playback of a cached URL failed."""
    invalidate_cached_stream_url(video_id, format_spec)
    return _resolve_and_cache(video_id, config, format_spec)
