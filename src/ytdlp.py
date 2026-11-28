"""yt-dlp options, feed/search/channel fetching, cancellation."""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from collections.abc import Callable

import yt_dlp

from src import channel_ref, feed_cache, innertube, logger
from src.cache import Cache
from src.cookies import get_cookiejar, invalidate
from src.entries import ChannelEntry, Entry, PlaylistEntry, VideoEntry
from src.errors import SignInRequired, SourceError, classify
from src.flat_entries import (
    FlatBatch,
    channel_info_row,
    collect_channel_playlists,
    subscribed_channel_row,
)
from src.plat import get_deps_bin


def _make_ydl(opts: dict, config, *, auth: bool = False) -> yt_dlp.YoutubeDL:
    """YoutubeDL; with ``auth`` it carries the browser's cookies (account-bound fetches only, see the mirror doc)."""
    ydl = yt_dlp.YoutubeDL(opts)
    jar = get_cookiejar(config) if auth else None
    if jar:
        ydl.cookiejar = jar
    return ydl


def base_opts(*, skip_manifests: bool = True) -> dict:
    """Base YoutubeDL options. ``skip_manifests=False`` keeps DASH/HLS data, which format selection needs."""
    deno_path = get_deps_bin() / ("deno.exe" if sys.platform == "win32" else "deno")
    opts: dict = {'quiet': True, 'no_warnings': True, 'socket_timeout': 30}
    if skip_manifests:
        opts['extractor_args'] = {'youtube': {'skip': ['dash', 'hls']}}
    if deno_path.exists():
        opts['js_runtimes'] = {'deno': {'path': str(deno_path)}}
    return opts


def _flat_opts(count: int) -> dict:
    """Options for metadata-only listing of up to ``count`` entries."""
    opts = base_opts()
    opts.update(
        extract_flat='in_playlist',
        lazy_playlist=True,
        source_address='0.0.0.0',
        geo_bypass=True,
        playlistend=count,
    )
    opts['extractor_args']['youtubetab'] = {'approximate_date': ['']}
    return opts


_cancel_events: set[threading.Event] = set()
_cancel_lock = threading.Lock()


def new_cancel_event() -> threading.Event:
    ev = threading.Event()
    with _cancel_lock:
        _cancel_events.add(ev)
    return ev


def release_cancel_event(ev: threading.Event) -> None:
    with _cancel_lock:
        _cancel_events.discard(ev)


def cancel_all() -> None:
    """Signal every active yt-dlp operation to stop, so workers blocked on network I/O unblock at exit."""
    with _cancel_lock:
        for ev in _cancel_events:
            ev.set()
        _cancel_events.clear()


_MAX_RETRIES = 1
_RETRY_DELAY_S = 2.0
MAX_SEARCH_RESULTS = 200

FEED_URLS = {
    "home":          "https://www.youtube.com/",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
    "yt_history":    "https://www.youtube.com/feed/history",
    "yt_watchlater": "https://www.youtube.com/playlist?list=WL",
}


def _extract_once(url: str, opts: dict, config, batch: FlatBatch, count: int, cancel: threading.Event,
                  *, auth: bool) -> tuple[bool, SourceError | None]:
    """One extraction into ``batch``: (yt-dlp returned no listing at all, the typed error if it failed)."""
    try:
        with _make_ydl(opts, config, auth=auth) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return True, None
            batch.read(info, count, cancel)
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("extract %s error: %s", url, exc)
        failure = classify(exc)
        if auth and isinstance(failure, SignInRequired):
            invalidate()
        return False, failure
    return False, None


def _extract_videos(
    url: str,
    config,
    cache: Cache,
    *,
    count: int,
    skip_ids: set[str],
    on_first_batch: Callable[[list[VideoEntry]], None] | None = None,
    first_batch_size: int = 15,
    auth: bool = False,
) -> tuple[list[VideoEntry], list[str]]:
    """Extract playable video entries from ``url``, caching each. Retries once on an empty result.

    A failed extraction raises a typed ``SourceError`` (``errors.classify``); an honestly empty feed returns ``[]``.

    The extractor window is ``count + len(skip_ids)``: skipped ids still occupy rows of the feed.
    Returns ``(entries, ids)``. ``on_first_batch`` fires once, when ``first_batch_size`` entries exist.
    """
    opts = _flat_opts(count + len(skip_ids))
    cancel = new_cancel_event()
    failure: SourceError | None = None
    try:
        for attempt in range(_MAX_RETRIES + 1):
            # A retry only follows an empty batch, so ``on_first_batch`` cannot have fired yet.
            batch = FlatBatch(cache, skip_ids, on_first_batch, first_batch_size)
            no_listing, failure = _extract_once(url, opts, config, batch, count, cancel, auth=auth)
            if no_listing or batch.entries or attempt >= _MAX_RETRIES:
                break
            logger.debug("extract %s: empty result, retrying (%d/%d)", url, attempt + 1, _MAX_RETRIES)
            time.sleep(_RETRY_DELAY_S)
    finally:
        release_cancel_event(cancel)
    if failure and not batch.entries:
        raise failure
    logger.debug("source: yt-dlp (%d entries)", len(batch.entries))
    return batch.entries, batch.ids


def fetch_page_batch(
    url: str,
    config,
    cache: Cache,
    *,
    skip_ids: set[str] | None = None,
    count: int = 80,
    feed_key: str | None = None,
    on_first_batch: Callable[[list[VideoEntry]], None] | None = None,
    first_batch_size: int = 15,
    auth: bool = False,
    cursor=None,
) -> list[VideoEntry]:
    """Up to ``count`` video entries from ``url`` minus ``skip_ids``; cache-first when ``feed_key`` is set.

    Blocking; run in a worker thread. ``on_first_batch`` gets the first ``first_batch_size`` entries early.
    With a ``cursor`` (``feed_cursor.FeedCursor``) the network read advances that open listing instead of
    starting a new one, and the caller keeps the cursor for the next batch.
    ``auth`` sends the browser's cookies (account feeds only: Home, YouTube history, Watch Later).
    """
    skip_ids = skip_ids or set()
    if feed_key:
        cached = feed_cache.cached_entries(cache, feed_key, skip_ids, count, feed_cache.MIN_FEED_COUNT)
        if cached is not None:
            logger.debug("source: cache (%d entries for %s)", len(cached), feed_key)
            return cached

    logger.debug("fetch_page_batch: fetching %s (count=%d, skip=%d)", url, count, len(skip_ids))
    if cursor is not None:
        results = cursor.take(count, skip_ids, on_first_batch=on_first_batch, first_batch_size=first_batch_size)
        if feed_key and len(cursor.ids) >= feed_cache.MIN_FEED_COUNT:
            cache.put_feed(feed_key, list(cursor.ids))
        return results
    results, all_ids = _extract_videos(
        url, config, cache, count=count, skip_ids=skip_ids,
        on_first_batch=on_first_batch, first_batch_size=first_batch_size, auth=auth,
    )
    if feed_key and len(all_ids) >= feed_cache.MIN_FEED_COUNT:
        cache.put_feed(feed_key, all_ids)
    return results


def fetch_search_batch(
    query: str,
    config,
    cache: Cache,
    *,
    skip_ids: set[str] | None = None,
    count: int = 50,
    on_first_batch: Callable[[list[Entry]], None] | None = None,
    sort: str = "relevance",
    kind: str = "all",
) -> list[Entry]:
    """Search results, cache-first, for a sort order and result type (each has its own cache entry).

    A cache hit returns every cached result not in ``skip_ids`` (up to ``MAX_SEARCH_RESULTS``), so a page
    beyond the first batch can be restored; ``count`` only limits a live fetch. ``on_first_batch`` fires early
    with the first page, never for a cache hit. yt-dlp is the fallback only for the plain search.
    """
    skip_ids = skip_ids or set()
    cache_key = feed_cache.search_cache_key(query, sort, kind)
    cached = feed_cache.cached_entries(cache, cache_key, skip_ids, MAX_SEARCH_RESULTS, feed_cache.MIN_SEARCH_COUNT)
    if cached is not None:
        logger.debug("source: cache (%d search results)", len(cached))
        return cached

    plain = sort == "relevance" and kind == "all"
    try:
        results = innertube.search(
            query, count=count, skip_ids=skip_ids, on_first_batch=on_first_batch, sort=sort, kind=kind
        )
    except SourceError as exc:
        if not plain:
            raise
        logger.debug("InnerTube search failed (%s); falling back to yt-dlp", exc.detail)
        results = []
    all_ids = [e["id"] for e in results]
    for entry in results:
        cache.put_video(entry)
    if results:
        logger.debug("source: innertube (%d search results)", len(results))
    if not results and plain:
        logger.debug("InnerTube search empty for %r; falling back to yt-dlp", query)
        results, all_ids = _extract_videos(
            f"ytsearch{count + len(skip_ids)}:{query}", config, cache, count=count, skip_ids=skip_ids,
            on_first_batch=on_first_batch,
        )
    feed_cache.remember_search(cache, cache_key, skip_ids, all_ids)
    return results


def fetch_channel_info(channel_url: str, config, cache: Cache) -> dict | None:
    """Channel name, description, subscriber count and avatar. Unauthenticated (public data)."""
    cache_key = "ch:info:" + hashlib.md5(channel_url.encode()).hexdigest()[:12]
    cached = cache.get_video(cache_key)
    if cached:
        return cached

    info = innertube.fetch_channel_info(channel_ref.base_url(channel_url))
    if info:
        info["_cache_key"] = cache_key
        cache.put_video(info)
        return info
    logger.debug("InnerTube channel info failed for %s; falling back to yt-dlp", channel_url)

    return _channel_info_from_ytdlp(channel_url, cache, cache_key)


def _channel_info_from_ytdlp(channel_url: str, cache: Cache, cache_key: str) -> dict | None:
    opts = base_opts()
    opts['extract_flat'] = 'in_playlist'
    opts['playlist_items'] = '0'

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(channel_url, download=False)
        if not data:
            return None
        info = {"_cache_key": cache_key, **channel_info_row(data, channel_url)}
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
) -> list[VideoEntry]:
    """Video entries from a channel. ``sort`` is ``date`` or ``views``."""
    url = channel_ref.base_url(channel_url) + ("/videos?sort=p" if sort == "views" else "/videos")
    logger.debug("fetch_channel_videos: url=%s sort=%s", url, sort)
    try:
        return fetch_page_batch(url, config, cache, count=count)
    except SourceError as exc:
        logger.debug("fetch_channel_videos: %s", exc.detail)
        return []


def fetch_channel_playlists(
    channel_url: str,
    config,
    cache: Cache,
    *,
    count: int = 80,
) -> list[PlaylistEntry]:
    url = channel_ref.base_url(channel_url) + "/playlists"
    logger.debug("fetch_channel_playlists: url=%s", url)

    results: list[PlaylistEntry] = []
    cancel = new_cancel_event()
    try:
        with _make_ydl(_flat_opts(count), config) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return results
            collect_channel_playlists(results, info, count, cancel)
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("fetch_channel_playlists error: %s", exc)
    finally:
        release_cancel_event(cancel)
    return results


def fetch_subscribed_channels(config, cache: Cache) -> list[ChannelEntry]:
    """The user's subscribed channels, cache-first. Needs cookies."""
    cache_key = "subs:channels"
    cached = cache.get_feed(cache_key)
    if cached:
        entries = [e for cid in cached for e in [cache.get_video_raw(cid)] if e]
        if entries:
            for e in entries:
                e["_is_channel"] = True
            return entries

    opts = _flat_opts(200)
    opts['socket_timeout'] = 60

    results: list[ChannelEntry] = []
    failure: SourceError | None = None
    for attempt in range(2):
        try:
            results = _list_subscribed_channels(opts, config, cache)
            failure = None
            break
        except yt_dlp.utils.DownloadError as exc:
            logger.debug("fetch_subscribed_channels error: %s", exc)
            failure = classify(exc)
            if attempt or not isinstance(failure, SignInRequired):
                break
            invalidate()
    if failure and not results:
        raise failure

    if results:
        cache.put_feed(cache_key, [e["id"] for e in results])
    return results


def _keep_channels(results: list[ChannelEntry], info: dict | None, cache: Cache, cancel: threading.Event) -> None:
    for data in ((info or {}).get('entries') or []):
        if cancel.is_set():
            return
        entry = subscribed_channel_row(data)
        if entry:
            cache.put_video(entry)
            results.append(entry)


def _list_subscribed_channels(opts: dict, config, cache: Cache) -> list[ChannelEntry]:
    """One authenticated pass over the subscriptions channel list; raises ``DownloadError``."""
    results: list[ChannelEntry] = []
    cancel = new_cancel_event()
    try:
        with _make_ydl(opts, config, auth=True) as ydl:
            info = ydl.extract_info("https://www.youtube.com/feed/channels", download=False)
            _keep_channels(results, info, cache, cancel)
    finally:
        release_cancel_event(cancel)
    return results


_warmup_done = threading.Event()


def warmup() -> None:
    """Load yt-dlp's extractor registry (~200-400 ms) off the main thread so the first fetch skips it."""
    if _warmup_done.is_set():
        return
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}):
            pass
    except Exception:
        pass
    finally:
        _warmup_done.set()
