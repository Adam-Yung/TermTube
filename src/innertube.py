"""YouTube InnerTube client: stdlib-only video metadata (~220 ms), channel browse, search and suggestions."""

from __future__ import annotations

import base64
import http.client
import json
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import Any, NamedTuple

from src import logger
from src.channel_ref import channel_id as channel_url_id
from src.entries import Entry, PlaylistEntry, VideoEntry
from src.errors import NetworkDown, RateLimited, SourceError
from src.innertube_pages import (
    browse_items,
    channel_info,
    mix_page,
    next_token,
    playlist_info,
    search_items,
    search_sections,
    video_details,
)
from src.innertube_rows import channel_video, playlist_item, playlist_video, short_video
from src.local_files import is_local_id

_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
_BROWSE_URL = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
_NEXT_URL = "https://www.youtube.com/youtubei/v1/next?prettyPrint=false"
_SEARCH_URL = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
_RESOLVE_URL = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
_WEB_CONTEXT: dict[str, Any] = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20260101.00.00",
        "hl": "en",
    }
}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "X-YouTube-Client-Name": "1",
    "X-YouTube-Client-Version": "2.20260101.00.00",
}
_local = threading.local()


def _connection(host: str, timeout: int) -> tuple[http.client.HTTPSConnection, bool]:
    """This thread's keep-alive connection to ``host`` (certificate-verified), and whether it already existed."""
    conns = _local.__dict__.setdefault("conns", {})
    conn = conns.get(host)
    reused = conn is not None
    if conn is None:
        conn = conns[host] = http.client.HTTPSConnection(host, timeout=timeout)
    conn.timeout = timeout
    if conn.sock:
        conn.sock.settimeout(timeout)
    return conn, reused


def _drop_connection(host: str) -> None:
    conn = _local.__dict__.get("conns", {}).pop(host, None)
    if conn:
        conn.close()


def _request(
    method: str, host: str, path: str, *, body: bytes | None, headers: dict, timeout: int, max_bytes: int | None = None
) -> tuple[int, bytes] | None:
    """One HTTPS request over a per-thread keep-alive connection: ``(status, body)``, or None on any error.

    A reused connection the server has closed fails on first use; that one failure is retried on a fresh connection.
    A body longer than ``max_bytes`` is cut there and the connection dropped (the rest is never read).
    """
    endpoint = path.split("?", 1)[0].rsplit("/", 1)[-1]
    for attempt in range(2):
        conn, reused = _connection(host, timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read() if max_bytes is None else resp.read(max_bytes)
            status = resp.status
        except (http.client.HTTPException, OSError) as exc:
            _drop_connection(host)
            if attempt == 0 and reused:
                continue
            logger.debug("%s %s failed: %s", method, endpoint, exc)
            return None
        if max_bytes is not None and len(data) >= max_bytes:
            _drop_connection(host)
        return status, data
    return None


_RETRY_DELAY_S = 1.0
_sleep = time.sleep
"""Pause before the one retry; tests replace it."""


def _post_once(url: str, payload: dict, timeout: int) -> dict | None:
    """One POST: the parsed reply, None for a final failure; raises ``RateLimited``/``NetworkDown`` when retryable."""
    parts = urllib.parse.urlsplit(url)
    path = f"{parts.path}?{parts.query}" if parts.query else parts.path
    reply = _request("POST", parts.netloc, path, body=json.dumps(payload).encode(), headers=_HEADERS, timeout=timeout)
    endpoint = parts.path.rsplit("/", 1)[-1]
    if reply is None:
        raise NetworkDown(f"innertube POST {endpoint}: no response")
    status, data = reply
    if status == 429:
        raise RateLimited(f"innertube POST {endpoint}: HTTP 429")
    if status >= 500:
        raise NetworkDown(f"innertube POST {endpoint}: HTTP {status}")
    if status != 200:
        logger.debug("innertube POST %s: HTTP %s", endpoint, status)
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        logger.debug("innertube POST %s: bad JSON: %s", endpoint, exc)
        return None


def _post_json(url: str, payload: dict, *, timeout: int = 8, strict: bool = False) -> dict | None:
    """POST JSON; the parsed response, or None on any error.

    A 429, a 5xx or a failed connection is retried once after ``_RETRY_DELAY_S``. With ``strict`` the second
    failure raises ``RateLimited``/``NetworkDown`` instead of returning None.
    """
    for attempt in range(2):
        try:
            return _post_once(url, payload, timeout)
        except SourceError as exc:
            logger.debug("%s%s", exc.detail, " (retrying)" if attempt == 0 else "")
            if attempt == 0:
                _sleep(_RETRY_DELAY_S)
            elif strict:
                raise
    return None


def fetch_video_details(video_id: str, *, timeout: int = 8) -> dict | None:
    """Video metadata from the /player API, shaped like a yt-dlp info dict (``_innertube`` is set). None on failure."""
    if is_local_id(video_id):
        return None
    payload = {
        "videoId": video_id,
        "context": _WEB_CONTEXT,
    }

    data = _post_json(_PLAYER_URL, payload, timeout=timeout)
    return video_details(data, video_id) if data else None


# Base64 protobuf tab selectors (field 2 is the tab name, field 110 carries the tab's number). Newest first for videos.
# shorts and live are [verify live]: built from the same pattern, not yet recorded.
_CHANNEL_TAB_PARAMS = {
    "videos": "EgZ2aWRlb3PyBgQKAjoA",
    "shorts": "EgZzaG9ydHPyBgUKA5oBAA==",
    "live": "EgdzdHJlYW1z8gYECgJ6AA==",
    "playlists": "EglwbGF5bGlzdHPyBgQKAkIA",
}
_TAB_PARSERS: dict[str, Callable[[dict], Entry | None]] = {
    "videos": channel_video,
    "shorts": short_video,
    "live": channel_video,
    "playlists": playlist_item,
}


class ChannelPage(NamedTuple):
    """One /browse page of a channel tab: its entries and the token for the next page (empty on the last)."""

    entries: list
    token: str = ""
    info: dict | None = None  # a playlist's first page: its header (``playlist_info``); None everywhere else


def fetch_channel_page(channel_id: str, tab: str = "videos", token: str = "", *, timeout: int = 12) -> ChannelPage:
    """One page of a channel tab (``CHANNEL_TABS``), or the page ``token`` points at. Empty on any failure."""
    if token:
        payload: dict = {"continuation": token, "context": _WEB_CONTEXT}
    else:
        payload = {"browseId": channel_id, "params": _CHANNEL_TAB_PARAMS[tab], "context": _WEB_CONTEXT}
    return _browse_page(payload, _TAB_PARSERS[tab], timeout)


def fetch_playlist_page(playlist_id: str, token: str = "", *, timeout: int = 12) -> ChannelPage:
    """One page (about 100 videos) of a playlist, or the page ``token`` points at. Empty on failure. [verify live]"""
    if token:
        payload: dict = {"continuation": token, "context": _WEB_CONTEXT}
    else:
        payload = {"browseId": "VL" + playlist_id, "context": _WEB_CONTEXT}
    header = None if token else lambda data: playlist_info(data, playlist_id)
    return _browse_page(payload, playlist_video, timeout, header)


def _browse_page(
    payload: dict, parse: Callable[[dict], Entry | None], timeout: int, header: Callable[[dict], dict] | None = None
) -> ChannelPage:
    data = _post_json(_BROWSE_URL, payload, timeout=timeout)
    if not data:
        return ChannelPage([])
    try:
        items = browse_items(data)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        logger.debug("innertube browse parse error: %s", exc)
        return ChannelPage([])
    entries = [e for e in map(parse, items) if e]
    logger.debug("innertube: %d browse entries", len(entries))
    return ChannelPage(entries, next_token(items), header(data) if header else None)


def fetch_channel_videos(channel_id: str, *, timeout: int = 12) -> list[VideoEntry]:
    """First page of newest-first channel videos (~600 ms for 30). Empty on failure."""
    return fetch_channel_page(channel_id, "videos", timeout=timeout).entries


def fetch_mix_page(playlist_id: str, token: str = "", *, timeout: int = 12) -> ChannelPage:
    """One page (about 25 videos) of a Mix (``RD…``): ``browse`` refuses those, ``next`` serves them anonymously.

    ``token`` is the watch endpoint of the last video of the page before; a Mix never ends, the caller's cap does.
    The first page carries the header (``mix: True``). A Mix that needs an account ("My Mix", ``RDMM``) comes back
    as an ``unavailable`` header. Recorded 2026-11-22 (``innertube_mix_next.json``). [verify live]
    """
    payload = json.loads(token) if token else {"playlistId": playlist_id}
    data = _post_json(_NEXT_URL, {**payload, "context": _WEB_CONTEXT}, timeout=timeout)
    return ChannelPage(*mix_page(data, playlist_id, not token))


_MAX_PLAYLIST_PAGES = 4
_MAX_SEARCH_PAGES = 12
_SORT_CODES = {"date": 2, "views": 3}
_TYPE_CODES = {"video": 1, "channel": 2, "playlist": 3}


def search_params(sort: str = "relevance", kind: str = "all") -> str:
    """The ``params`` blob of a /search request for a sort order and a result type; empty for the defaults.

    A protobuf message, base64: field 1 is the sort code, field 2 holds the filter whose field 2 is the type.
    The single-filter blobs (``CAI=``, ``EgIQAQ==`` ...) are the documented ones; the combined ones are those two
    messages joined, not yet seen working live [verify live].
    """
    raw = bytes([0x08, _SORT_CODES[sort]]) if sort in _SORT_CODES else b""
    if kind in _TYPE_CODES:
        raw += bytes([0x12, 0x02, 0x10, _TYPE_CODES[kind]])
    return base64.b64encode(raw).decode()


def search(
    query: str,
    *,
    count: int = 50,
    skip_ids: set[str] | None = None,
    on_first_batch: Callable[[list[Entry]], None] | None = None,
    sort: str = "relevance",
    kind: str = "all",
) -> list[Entry]:
    """Results for ``query`` through InnerTube ``/search``: videos, and with ``kind`` ``all``/``channel``/``playlist``
    channel and playlist rows. ``sort`` is ``relevance``/``date``/``views``. Anonymous. Empty on a bad reply; a failed
    first page (after one retry) raises ``RateLimited``/``NetworkDown``.

    Follows continuation tokens until ``count`` entries are collected or ``_MAX_SEARCH_PAGES`` pages are read.
    ``on_first_batch`` receives the first page's entries as soon as that page arrives.
    """
    skip_ids = skip_ids or set()
    payload: dict = {"query": query, "context": _WEB_CONTEXT}
    if params := search_params(sort, kind):
        payload["params"] = params
    results: list[Entry] = []
    seen = set(skip_ids)
    for _ in range(_MAX_SEARCH_PAGES):
        data = _post_json(_SEARCH_URL, payload, strict=not results)
        if not data:
            break
        entries, token = search_items(search_sections(data))
        for entry in entries:
            if entry["id"] not in seen:
                seen.add(entry["id"])
                results.append(entry)
        if on_first_batch and results:
            on_first_batch(list(results))
            on_first_batch = None
        if len(results) >= count or not token:
            break
        payload = {"continuation": token, "context": _WEB_CONTEXT}
    return results[:count]


def resolve_channel_id(channel_url: str) -> str | None:
    """The ``UC…`` id for a channel URL (``/channel/UC…``, ``/@handle``, ``/user/…``, ``/c/…``)."""
    known = channel_url_id(channel_url)
    if known:
        return known
    data = _post_json(_RESOLVE_URL, {"url": channel_url, "context": _WEB_CONTEXT})
    browse = ((data or {}).get("endpoint") or {}).get("browseEndpoint") or {}
    browse_id = browse.get("browseId", "")
    return browse_id if browse_id.startswith("UC") else None


def fetch_channel_info(channel_url: str) -> dict | None:
    """Channel name, description, subscriber count and avatar from InnerTube. Anonymous.

    Same keys as ``ytdlp.fetch_channel_info`` (minus the cache key). None on failure.
    """
    channel_id = resolve_channel_id(channel_url)
    if not channel_id:
        return None
    data = _post_json(_BROWSE_URL, {"browseId": channel_id, "context": _WEB_CONTEXT})
    return channel_info(data, channel_id)


def fetch_channel_playlists(channel_id: str, *, count: int = 80, timeout: int = 12) -> list[PlaylistEntry]:
    """Playlists of a channel from /browse, following continuations up to ``count``. Anonymous. Empty on failure."""
    entries: list[PlaylistEntry] = []
    token = ""
    for _ in range(_MAX_PLAYLIST_PAGES):
        page = fetch_channel_page(channel_id, "playlists", token, timeout=timeout)
        entries.extend(page.entries)
        token = page.token
        if len(entries) >= count or not token:
            break
    return entries[:count]


_SUGGEST_HOST = "suggestqueries.google.com"
_SUGGEST_MAX_BYTES = 16 * 1024
_SUGGEST_TIMEOUT = 2
_SUGGEST_HEADERS = {"User-Agent": _HEADERS["User-Agent"], "Accept": "application/json"}


def parse_suggestions(raw: bytes | str) -> list[str]:
    """Suggestion strings from a suggest reply ``[query, [suggestion, ...], ...]``; empty for anything else."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    items = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    return [s.strip() for s in items if isinstance(s, str) and s.strip()]


def fetch_suggestions(query: str, *, timeout: int = _SUGGEST_TIMEOUT) -> list[str]:
    """YouTube search suggestions for ``query`` from Google's anonymous suggest endpoint.

    Sends the partial text only: no cookies, no account, certificate-verified TLS. Empty on any failure.
    """
    path = "/complete/search?" + urllib.parse.urlencode({"client": "firefox", "ds": "yt", "q": query})
    reply = _request("GET", _SUGGEST_HOST, path, body=None, headers=_SUGGEST_HEADERS,
                     timeout=timeout, max_bytes=_SUGGEST_MAX_BYTES)
    if reply is None or reply[0] != 200:
        return []
    return parse_suggestions(reply[1])
