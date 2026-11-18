"""yt-dlp options, feed/search/channel fetching, cancellation."""

from __future__ import annotations

import hashlib
import re
import sys
import threading
import time
from collections.abc import Callable

import yt_dlp

from src import innertube, logger
from src.cache import Cache
from src.cookies import get_cookiejar, invalidate, is_auth_failure
from src.entries import ChannelEntry, Entry, PlaylistEntry, VideoEntry
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
_MIN_FEED_COUNT = 15
_MIN_SEARCH_COUNT = 5
MAX_SEARCH_RESULTS = 200

FEED_URLS = {
    "home":          "https://www.youtube.com/",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}

_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _is_playable_video(entry: VideoEntry) -> bool:
    if not _VIDEO_ID_RE.match(entry.get("id", "")):
        return False
    return entry.get("_type", "video") not in ("playlist", "channel")


def _normalise_entry(entry: VideoEntry) -> VideoEntry:
    """Ensure flat-playlist entries have 'thumbnail' and 'webpage_url' fields."""
    entry.setdefault("webpage_url", f"https://www.youtube.com/watch?v={entry.get('id', '')}")
    if not entry.get("thumbnail"):
        from src.ui.thumbnail import best_thumb_url
        url = best_thumb_url(entry)
        if url:
            entry["thumbnail"] = url
    return entry


def _cached_entries(
    cache: Cache, key: str, skip_ids: set[str], count: int, minimum: int
) -> list[VideoEntry] | None:
    """Entries of the cached feed ``key`` minus ``skip_ids``, or None if too few are usable."""
    cached_ids = cache.get_feed(key)
    if not cached_ids or len(cached_ids) < minimum:
        return None
    results: list[VideoEntry] = []
    for vid_id in cached_ids:
        if vid_id in skip_ids:
            continue
        if len(results) >= count:
            break
        entry = cache.get_video_raw(vid_id)
        if entry:
            results.append(entry)
    if len(results) >= minimum:
        logger.debug("cache hit for '%s' (%d entries)", key, len(results))
        return results
    return None


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

    The extractor window is ``count + len(skip_ids)``: skipped ids still occupy rows of the feed.
    Returns ``(entries, ids)``. ``on_first_batch`` fires once, when ``first_batch_size`` entries exist.
    """
    opts = _flat_opts(count + len(skip_ids))
    results: list[VideoEntry] = []
    all_ids: list[str] = []

    cancel = new_cancel_event()
    try:
        for attempt in range(_MAX_RETRIES + 1):
            results = []
            all_ids = []
            try:
                with _make_ydl(opts, config, auth=auth) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        break
                    for entry in (info.get('entries') or []):
                        if cancel.is_set() or len(results) >= count:
                            break
                        if entry is None or not _is_playable_video(entry):
                            continue
                        _normalise_entry(entry)
                        vid = entry.get("id", "")
                        if vid in skip_ids:
                            continue
                        cache.put_video(entry)
                        all_ids.append(vid)
                        results.append(entry)
                        if on_first_batch and len(results) == first_batch_size:
                            on_first_batch(list(results))
                            on_first_batch = None
            except yt_dlp.utils.DownloadError as exc:
                logger.debug("extract %s error: %s", url, exc)
                if auth and is_auth_failure(exc):
                    invalidate()

            if results or attempt >= _MAX_RETRIES:
                break
            logger.debug("extract %s: empty result, retrying (%d/%d)", url, attempt + 1, _MAX_RETRIES)
            time.sleep(_RETRY_DELAY_S)
    finally:
        release_cancel_event(cancel)
    return results, all_ids


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
) -> list[VideoEntry]:
    """Up to ``count`` video entries from ``url`` minus ``skip_ids``; cache-first when ``feed_key`` is set.

    Blocking; run in a worker thread. ``on_first_batch`` gets the first ``first_batch_size`` entries early.
    ``auth`` sends the browser's cookies (home feed only).
    """
    skip_ids = skip_ids or set()
    if feed_key:
        cached = _cached_entries(cache, feed_key, skip_ids, count, _MIN_FEED_COUNT)
        if cached is not None:
            return cached

    logger.debug("fetch_page_batch: fetching %s (count=%d, skip=%d)", url, count, len(skip_ids))
    results, all_ids = _extract_videos(
        url, config, cache, count=count, skip_ids=skip_ids,
        on_first_batch=on_first_batch, first_batch_size=first_batch_size, auth=auth,
    )
    if feed_key and len(all_ids) >= _MIN_FEED_COUNT:
        cache.put_feed(feed_key, all_ids)
    return results


def _search_cache_key(query: str, sort: str, kind: str) -> str:
    return "search_" + hashlib.md5(f"{query.lower().strip()}|{sort}|{kind}".encode()).hexdigest()[:10]


def _remember_search(cache: Cache, key: str, skip_ids: set[str], new_ids: list[str]) -> None:
    """Store the id list of a search; an extension batch is appended to the ids already cached under ``key``."""
    ids = new_ids
    if skip_ids:
        known = cache.get_feed(key)
        if not known:  # the order of what is already shown is unknown: leave the next load to refetch
            return
        ids = known + [i for i in new_ids if i not in known]
    if len(ids) >= _MIN_SEARCH_COUNT:
        cache.put_feed(key, ids)


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
    cache_key = _search_cache_key(query, sort, kind)
    cached = _cached_entries(cache, cache_key, skip_ids, MAX_SEARCH_RESULTS, _MIN_SEARCH_COUNT)
    if cached is not None:
        return cached

    results = innertube.search(
        query, count=count, skip_ids=skip_ids, on_first_batch=on_first_batch, sort=sort, kind=kind
    )
    all_ids = [e["id"] for e in results]
    for entry in results:
        cache.put_video(entry)
    if not results and sort == "relevance" and kind == "all":
        logger.debug("InnerTube search empty for %r; falling back to yt-dlp", query)
        results, all_ids = _extract_videos(
            f"ytsearch{count + len(skip_ids)}:{query}", config, cache, count=count, skip_ids=skip_ids,
            on_first_batch=on_first_batch,
        )
    _remember_search(cache, cache_key, skip_ids, all_ids)
    return results


_CH_SUFFIX_RE = re.compile(
    r"/(videos|shorts|streams|playlists|community|about|featured|membership|store)(/.*)?$",
    re.IGNORECASE,
)


def _normalise_channel_url(url: str) -> str:
    """Strip any existing channel-tab path component from a YouTube channel URL."""
    return _CH_SUFFIX_RE.sub("", url.rstrip("/"))


def fetch_channel_info(channel_url: str, config, cache: Cache) -> dict | None:
    """Channel name, description, subscriber count and avatar. Unauthenticated (public data)."""
    cache_key = "ch:info:" + hashlib.md5(channel_url.encode()).hexdigest()[:12]
    cached = cache.get_video(cache_key)
    if cached:
        return cached

    info = innertube.fetch_channel_info(_normalise_channel_url(channel_url))
    if info:
        info["_cache_key"] = cache_key
        cache.put_video(info)
        return info
    logger.debug("InnerTube channel info failed for %s; falling back to yt-dlp", channel_url)

    opts = base_opts()
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
) -> list[VideoEntry]:
    """Video entries from a channel. ``sort`` is ``date`` or ``views``."""
    url = _normalise_channel_url(channel_url) + ("/videos?sort=p" if sort == "views" else "/videos")
    logger.debug("fetch_channel_videos: url=%s sort=%s", url, sort)
    return fetch_page_batch(url, config, cache, count=count)


def fetch_channel_playlists(
    channel_url: str,
    config,
    cache: Cache,
    *,
    count: int = 80,
) -> list[PlaylistEntry]:
    url = _normalise_channel_url(channel_url) + "/playlists"
    logger.debug("fetch_channel_playlists: url=%s", url)

    results: list[PlaylistEntry] = []
    cancel = new_cancel_event()
    try:
        with _make_ydl(_flat_opts(count), config) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return results
            for entry in (info.get('entries') or []):
                if cancel.is_set() or len(results) >= count:
                    break
                if entry is None:
                    continue
                if entry.get("_type", "") not in ("playlist", "url") and not entry.get("id"):
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
    for attempt in range(2):
        try:
            results = _list_subscribed_channels(opts, config, cache)
            break
        except yt_dlp.utils.DownloadError as exc:
            logger.debug("fetch_subscribed_channels error: %s", exc)
            if attempt or not is_auth_failure(exc):
                break
            invalidate()

    if results:
        cache.put_feed(cache_key, [e["id"] for e in results])
    return results


def _list_subscribed_channels(opts: dict, config, cache: Cache) -> list[ChannelEntry]:
    """One authenticated pass over the subscriptions channel list; raises ``DownloadError``."""
    results: list[ChannelEntry] = []
    cancel = new_cancel_event()
    try:
        with _make_ydl(opts, config, auth=True) as ydl:
            info = ydl.extract_info("https://www.youtube.com/feed/channels", download=False)
            for data in ((info or {}).get('entries') or []):
                if cancel.is_set():
                    break
                if data is None:
                    continue
                cid = data.get("id") or data.get("channel_id") or ""
                if not cid:
                    continue
                name = data.get("title") or data.get("channel") or data.get("uploader") or cid
                ch_url = data.get("url") or data.get("channel_url") or ""
                entry = {
                    "id": cid, "title": name, "channel": name,
                    "channel_url": ch_url, "channel_id": cid,
                    "uploader": name, "uploader_url": ch_url,
                    "subscriber_count": data.get("channel_follower_count"),
                    "video_count": data.get("playlist_count"),
                    "thumbnail": data.get("thumbnail") or "",
                    "description": data.get("description") or "",
                    "_is_channel": True,
                }
                cache.put_video(entry)
                results.append(entry)
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
