"""Latest uploads of a channel: the public RSS feed, with InnerTube ``/browse`` as the fallback."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable

from src import innertube, logger

_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_MAX_BYTES = 1_000_000
_DEAD_AFTER_404S = 2
_DEAD_FOR_S = 30 * 60

_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "m": "http://search.yahoo.com/mrss/",
}


class _DeadFlag:
    """Counts consecutive RSS 404s; after ``_DEAD_AFTER_404S`` RSS is skipped for ``_DEAD_FOR_S`` seconds."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._misses = 0
        self._dead_since: float | None = None

    def is_dead(self) -> bool:
        with self._lock:
            if self._dead_since is None:
                return False
            if self._clock() - self._dead_since >= _DEAD_FOR_S:
                self._dead_since, self._misses = None, 0
                return False
            return True

    def record(self, *, not_found: bool) -> None:
        with self._lock:
            if not not_found:
                self._misses = 0
                return
            self._misses += 1
            if self._misses >= _DEAD_AFTER_404S:
                self._dead_since = self._clock()


_rss_state = _DeadFlag()


def parse_atom(xml_bytes: bytes) -> list[dict]:
    """Video entries of a channel Atom feed, newest first as the feed lists them. Empty on malformed XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    channel = root.findtext("a:title", "", _NS)
    entries = []
    for node in root.findall("a:entry", _NS):
        video_id = node.findtext("yt:videoId", "", _NS)
        if not video_id:
            continue
        stats = node.find("m:group/m:community/m:statistics", _NS)
        thumb = node.find("m:group/m:thumbnail", _NS)
        views = stats.get("views", "") if stats is not None else ""
        entries.append({
            "id": video_id,
            "title": node.findtext("a:title", "", _NS),
            "upload_date": node.findtext("a:published", "", _NS)[:10].replace("-", "") or None,
            "channel": channel,
            "uploader": channel,
            "view_count": int(views) if views.isdigit() else None,
            "thumbnail": thumb.get("url", "") if thumb is not None else "",
            "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
            "_type": "url",
        })
    return entries


def _fetch_rss(channel_id: str, timeout: int = 8) -> list[dict]:
    """Anonymous GET of the feed. Empty on any failure; 404s feed the dead flag."""
    req = urllib.request.Request(_RSS_URL.format(channel_id), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(_MAX_BYTES)
    except urllib.error.HTTPError as exc:
        _rss_state.record(not_found=exc.code == 404)
        logger.debug("rss %s: HTTP %s", channel_id, exc.code)
        return []
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.debug("rss %s failed: %s", channel_id, exc)
        return []
    _rss_state.record(not_found=False)
    return parse_atom(body)


def channel_latest(channel_id: str) -> list[dict]:
    """Latest uploads of ``channel_id``: RSS unless it is known dead, then InnerTube. Anonymous."""
    if not _rss_state.is_dead():
        entries = _fetch_rss(channel_id)
        if entries:
            return entries
    return innertube.fetch_channel_videos(channel_id)
