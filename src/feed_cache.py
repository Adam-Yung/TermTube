"""The cached id lists behind feeds and searches: when a list is good enough to show, and what gets stored."""

from __future__ import annotations

import hashlib

from src import logger
from src.cache import Cache
from src.entries import VideoEntry

MIN_FEED_COUNT = 15
MIN_SEARCH_COUNT = 5


def cached_entries(
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


def search_cache_key(query: str, sort: str, kind: str) -> str:
    return "search_" + hashlib.md5(f"{query.lower().strip()}|{sort}|{kind}".encode()).hexdigest()[:10]


def remember_search(cache: Cache, key: str, skip_ids: set[str], new_ids: list[str]) -> None:
    """Store the id list of a search; an extension batch is appended to the ids already cached under ``key``."""
    ids = new_ids
    if skip_ids:
        known = cache.get_feed(key)
        if not known:  # the order of what is already shown is unknown: leave the next load to refetch
            return
        ids = known + [i for i in new_ids if i not in known]
    if len(ids) >= MIN_SEARCH_COUNT:
        cache.put_feed(key, ids)
