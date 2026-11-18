"""YouTube InnerTube client: stdlib-only video metadata (~220 ms) and channel browse."""

from __future__ import annotations

import base64
import http.client
import json
import re
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import Any, NamedTuple

from src import logger
from src.channel_ref import channel_id as channel_url_id
from src.entries import ChannelEntry, Entry, PlaylistEntry, VideoEntry
from src.errors import NetworkDown, RateLimited, SourceError

_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
_BROWSE_URL = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"

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
    payload = {
        "videoId": video_id,
        "context": _WEB_CONTEXT,
    }

    data = _post_json(_PLAYER_URL, payload, timeout=timeout)
    if not data:
        return None

    vd = data.get("videoDetails")
    if not vd:
        logger.debug("innertube: no videoDetails for %s (keys: %s)",
                     video_id, list(data.keys())[:5])
        return None

    mf = data.get("microformat", {}).get("playerMicroformatRenderer", {})

    # yt-dlp convention: YYYYMMDD
    upload_date = mf.get("uploadDate") or mf.get("publishDate")
    if upload_date and "T" in upload_date:
        upload_date = upload_date.split("T")[0]
    if upload_date:
        upload_date = upload_date.replace("-", "")

    owner_url = mf.get("ownerProfileUrl", "")
    uploader_id = ""
    if "/@" in owner_url:
        uploader_id = "@" + owner_url.split("/@", 1)[1].rstrip("/")

    return {
        "id": video_id,
        "title": vd.get("title", ""),
        "description": vd.get("shortDescription", ""),
        "view_count": _parse_int(vd.get("viewCount")),
        "like_count": _parse_int(mf.get("likeCount")),
        "upload_date": upload_date,
        "channel": vd.get("author", ""),
        "channel_id": vd.get("channelId", ""),
        "channel_url": f"https://www.youtube.com/channel/{vd.get('channelId', '')}",
        "uploader": vd.get("author", ""),
        "uploader_id": uploader_id,
        "uploader_url": owner_url.replace("http://", "https://") if owner_url else "",
        "duration": _parse_int(vd.get("lengthSeconds")),
        "categories": [mf.get("category", "")] if mf.get("category") else [],
        "is_live": vd.get("isLiveContent", False),
        "keywords": vd.get("keywords", []),
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_innertube": True,
    }


CHANNEL_TABS = ("videos", "shorts", "live", "playlists")
# Base64 protobuf tab selectors (field 2 is the tab name, field 110 carries the tab's number). Newest first for videos.
# shorts and live are [verify live]: built from the same pattern, not yet recorded.
_CHANNEL_TAB_PARAMS = {
    "videos": "EgZ2aWRlb3PyBgQKAjoA",
    "shorts": "EgZzaG9ydHPyBgUKA5oBAA==",
    "live": "EgdzdHJlYW1z8gYECgJ6AA==",
    "playlists": "EglwbGF5bGlzdHPyBgQKAkIA",
}


class ChannelPage(NamedTuple):
    """One /browse page of a channel tab: its entries and the token for the next page (empty on the last)."""

    entries: list
    token: str = ""


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
    return _browse_page(payload, _parse_playlist_video, timeout)


def _browse_page(payload: dict, parse: Callable[[dict], Entry | None], timeout: int) -> ChannelPage:
    data = _post_json(_BROWSE_URL, payload, timeout=timeout)
    if not data:
        return ChannelPage([])
    try:
        items = _browse_items(data)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        logger.debug("innertube browse parse error: %s", exc)
        return ChannelPage([])
    entries = [e for e in map(parse, items) if e]
    logger.debug("innertube: %d browse entries", len(entries))
    return ChannelPage(entries, _next_token(items))


def fetch_channel_videos(channel_id: str, *, timeout: int = 12) -> list[VideoEntry]:
    """First page of newest-first channel videos (~600 ms for 30). Empty on failure."""
    return fetch_channel_page(channel_id, "videos", timeout=timeout).entries


def _browse_items(data: dict) -> list[dict]:
    """The grid items of a first /browse response (rich grid or playlist grid) or of a continuation response."""
    actions = data.get("onResponseReceivedActions")
    if actions:
        return actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    selected = next((t["tabRenderer"] for t in tabs if t.get("tabRenderer", {}).get("selected")), {})
    content = selected.get("content", {})
    if "richGridRenderer" in content:
        return content["richGridRenderer"].get("contents", [])
    sections = content.get("sectionListRenderer", {}).get("contents", [])
    rows = [c for s in sections for c in s.get("itemSectionRenderer", {}).get("contents", [])]
    for row in rows:
        if "playlistVideoListRenderer" in row:
            return row["playlistVideoListRenderer"].get("contents", [])
    if any("lockupViewModel" in row for row in rows):  # a playlist page: videos, with the token in the section list
        return rows + [c for c in sections if "continuationItemViewModel" in c]
    return [i for c in rows for i in c.get("gridRenderer", {}).get("items", [])]


def _next_token(items: list[dict]) -> str:
    for item in items:
        if "continuationItemRenderer" in item:
            command = item["continuationItemRenderer"].get("continuationEndpoint", {})
            return command.get("continuationCommand", {}).get("token", "")
        if "continuationItemViewModel" in item:
            command = item["continuationItemViewModel"].get("continuationCommand", {}).get("innertubeCommand", {})
            return command.get("continuationCommand", {}).get("token", "")
    return ""


def _parse_channel_video_item(item: dict) -> VideoEntry | None:
    """One /browse richGridRenderer item as a video entry, or None if it is not a video."""
    ri = item.get("richItemRenderer", {})
    if not ri:
        return None
    return _video_from_lockup(ri.get("content", {}).get("lockupViewModel", {}))


def _video_from_lockup(lvm: dict) -> VideoEntry | None:
    """A video entry from a ``lockupViewModel`` (channel grids and playlist pages share it), or None without an id."""
    if not lvm:
        return None

    video_id = lvm.get("contentId", "")
    if not video_id:
        return None

    meta = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = meta.get("title", {}).get("content", "")

    view_count_text = ""
    published_text = ""
    meta_rows = (meta.get("metadata", {})
                 .get("contentMetadataViewModel", {})
                 .get("metadataRows", []))
    for row in meta_rows:
        for part in row.get("metadataParts", []):
            text = part.get("text", {}).get("content", "")
            if "view" in text.lower() or "watching" in text.lower():
                view_count_text = text
            elif "ago" in text.lower() or "streamed" in text.lower():
                published_text = text

    duration_text = ""
    is_live = False
    overlays = (lvm.get("contentImage", {})
                .get("thumbnailViewModel", {})
                .get("overlays", []))
    for ov in overlays:
        tbov = ov.get("thumbnailBottomOverlayViewModel", {})
        if tbov:
            for badge in tbov.get("badges", []):
                bvm = badge.get("thumbnailBadgeViewModel", {})
                text = bvm.get("text", "")
                if text.upper() == "LIVE":
                    is_live = True
                elif text and ":" in text:
                    duration_text = text
                    break
        if duration_text:
            break

    thumbnail = ""
    sources = (lvm.get("contentImage", {})
               .get("thumbnailViewModel", {})
               .get("image", {})
               .get("sources", []))
    if sources:
        thumbnail = sources[-1].get("url", "")

    entry: VideoEntry = {
        "id": video_id,
        "title": title,
        "view_count_text": view_count_text,
        "published_text": published_text,
        "duration_text": duration_text,
        "view_count": _parse_view_count(view_count_text),
        "duration": _parse_duration_text(duration_text),
        "thumbnail": thumbnail,
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_type": "url",
    }
    if is_live:
        entry["is_live"] = True
    return entry


def _parse_short_item(item: dict) -> VideoEntry | None:
    """One Shorts-tab ``shortsLockupViewModel`` item as a video entry. [verify live]"""
    vm = item.get("richItemRenderer", {}).get("content", {}).get("shortsLockupViewModel", {})
    command = vm.get("onTap", {}).get("innertubeCommand", {})
    video_id = command.get("reelWatchEndpoint", {}).get("videoId") or vm.get("entityId", "").removeprefix(
        "shorts-shelf-item-"
    )
    if not video_id:
        return None
    meta = vm.get("overlayMetadata", {})
    views_text = meta.get("secondaryText", {}).get("content", "")
    sources = vm.get("thumbnail", {}).get("sources", [])
    return {
        "id": video_id,
        "title": meta.get("primaryText", {}).get("content", ""),
        "view_count_text": views_text,
        "view_count": _parse_view_count(views_text),
        "thumbnail": sources[-1].get("url", "") if sources else "",
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_type": "url",
    }


def _parse_view_count(text: str) -> int | None:
    """Parse view count from text like '105K views' or '1.2M views'."""
    if not text:
        return None
    match = re.search(r"([\d,.]+)\s*([KMB]?)", text)
    if not match:
        return None
    num_str = match.group(1).replace(",", "")
    try:
        num = float(num_str)
    except ValueError:
        return None
    multiplier = match.group(2)
    if multiplier == "K":
        num *= 1000
    elif multiplier == "M":
        num *= 1_000_000
    elif multiplier == "B":
        num *= 1_000_000_000
    return int(num)


def _parse_duration_text(text: str) -> int | None:
    """Parse duration from text like '3:45' or '1:02:30' to seconds."""
    if not text:
        return None
    parts = text.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except ValueError:
        pass
    return None


def _parse_int(value) -> int | None:
    """Safely parse a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


_MAX_PLAYLIST_PAGES = 4
_VIDEO_COUNT = re.compile(r"^[\d,]+ videos?$")

_SEARCH_URL = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
_RESOLVE_URL = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
_MAX_SEARCH_PAGES = 12
_SORT_CODES = {"date": 2, "views": 3}
_TYPE_CODES = {"video": 1, "channel": 2, "playlist": 3}
_SUBSCRIBERS_WORD = re.compile(r"subscribers?", re.IGNORECASE)


def _text(node: dict | None) -> str:
    """Plain text of an InnerTube text node (``simpleText`` or ``runs``)."""
    if not node:
        return ""
    return node.get("simpleText") or "".join(r.get("text", "") for r in node.get("runs", []))


def _parse_search_video(vr: dict) -> VideoEntry | None:
    video_id = vr.get("videoId")
    if not video_id:
        return None
    owner = vr.get("ownerText") or vr.get("longBylineText") or {}
    browse = ((owner.get("runs") or [{}])[0].get("navigationEndpoint") or {}).get("browseEndpoint") or {}
    thumbs = (vr.get("thumbnail") or {}).get("thumbnails") or []
    badges = {b.get("metadataBadgeRenderer", {}).get("style", "") for b in vr.get("badges") or []}
    name = _text(owner)
    channel_id = browse.get("browseId", "")
    return {
        "id": video_id,
        "title": _text(vr.get("title")),
        "uploader": name,
        "channel": name,
        "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else "",
        "duration": _parse_duration_text(_text(vr.get("lengthText"))),
        "view_count": _parse_view_count(_text(vr.get("viewCountText"))),
        "published_text": _text(vr.get("publishedTimeText")),
        "thumbnail": thumbs[-1].get("url", "") if thumbs else "",
        "is_live": "BADGE_STYLE_TYPE_LIVE_NOW" in badges,
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_type": "url",
    }


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


def _https(url: str) -> str:
    return "https:" + url if url.startswith("//") else url


def _parse_search_channel(cr: dict) -> ChannelEntry | None:
    channel_id = cr.get("channelId")
    if not channel_id:
        return None
    name = _text(cr.get("title"))
    thumbs = (cr.get("thumbnail") or {}).get("thumbnails") or []
    handle = ((cr.get("navigationEndpoint") or {}).get("browseEndpoint") or {}).get("canonicalBaseUrl", "")
    url = f"https://www.youtube.com{handle}" if handle.startswith("/") else f"https://www.youtube.com/channel/{channel_id}"
    # The subscriber count sits in one of two fields depending on the page version; the other holds the @handle.
    texts = [_text(cr.get("subscriberCountText")), _text(cr.get("videoCountText"))]
    subs = next((t for t in texts if _SUBSCRIBERS_WORD.search(t)), "")
    return {
        "id": channel_id, "title": name, "channel": name, "channel_id": channel_id, "channel_url": url,
        "uploader": name, "uploader_url": url, "subscriber_count": _parse_view_count(subs),
        "thumbnail": _https(thumbs[-1].get("url", "")) if thumbs else "",
        "description": _text(cr.get("descriptionSnippet")), "_is_channel": True,
    }


def _parse_search_playlist(pr: dict) -> PlaylistEntry | None:
    playlist_id = pr.get("playlistId")
    if not playlist_id:
        return None
    title = _text(pr.get("title")) or playlist_id
    thumbs = ((pr.get("thumbnails") or [{}])[0].get("thumbnails")) or []
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    return {
        "id": playlist_id, "title": title, "url": url, "webpage_url": url,
        "uploader": _text(pr.get("shortBylineText")), "thumbnail": _https(thumbs[-1].get("url", "")) if thumbs else "",
        "playlist_count": _parse_view_count(str(pr.get("videoCount", ""))),
        "_type": "playlist", "_is_playlist": True, "_playlist_name": title,
    }


def _parse_search_item(item: dict) -> Entry | None:
    """One search row (video, channel or playlist) as an entry; None for shelves, ads and anything else."""
    if "videoRenderer" in item:
        return _parse_search_video(item["videoRenderer"])
    if "channelRenderer" in item:
        return _parse_search_channel(item["channelRenderer"])
    if "playlistRenderer" in item:
        return _parse_search_playlist(item["playlistRenderer"])
    return _parse_playlist_item(item)


def _search_items(sections: list[dict]) -> tuple[list[Entry], str]:
    """Result entries and the next continuation token from a list of result sections."""
    entries: list[Entry] = []
    token = ""
    for section in sections:
        for item in section.get("itemSectionRenderer", {}).get("contents", []):
            entry = _parse_search_item(item)
            if entry:
                entries.append(entry)
        cont = section.get("continuationItemRenderer", {})
        token = cont.get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", token)
    return entries, token


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
        if "contents" in data:
            sections = (data["contents"].get("twoColumnSearchResultsRenderer", {})
                        .get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", []))
        else:
            actions = data.get("onResponseReceivedCommands") or [{}]
            sections = actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
        entries, token = _search_items(sections)
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


def _find_text(node, pattern: re.Pattern) -> str:
    """First string anywhere under ``node`` that matches ``pattern``."""
    if isinstance(node, str):
        return node if pattern.search(node) else ""
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
    for child in children:
        found = _find_text(child, pattern)
        if found:
            return found
    return ""


_SUBSCRIBERS = re.compile(r"^[\d.,]+\s*[KMB]?\s+subscribers?$", re.IGNORECASE)


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
    meta = ((data or {}).get("metadata") or {}).get("channelMetadataRenderer")
    if not meta:
        return None
    avatars = (meta.get("avatar") or {}).get("thumbnails") or []
    return {
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "channel": meta.get("title", ""),
        "channel_id": channel_id,
        "description": meta.get("description", ""),
        "subscriber_count": _parse_view_count(_find_text(data.get("header", {}), _SUBSCRIBERS)),
        "thumbnail": avatars[-1].get("url", "") if avatars else "",
        "uploader_url": (meta.get("vanityChannelUrl") or "").replace("http://", "https://"),
        "video_count": _parse_view_count(_find_text(data.get("header", {}), _VIDEO_COUNT)),
        "joined": _find_text(data.get("header", {}), _JOINED),
        "tabs": _channel_tabs(data),
    }


def _channel_tabs(data: dict) -> list[str]:
    """Which of ``CHANNEL_TABS`` the channel has, from the tab titles of the first /browse response."""
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    titles = {t.get("tabRenderer", {}).get("title", "").lower() for t in tabs}
    return [tab for tab in CHANNEL_TABS if tab in titles]


def _parse_playlist_item(item: dict) -> PlaylistEntry | None:
    """One ``lockupViewModel`` grid item as a playlist entry, or None for any other content type."""
    lvm = item.get("lockupViewModel") or {}
    playlist_id = lvm.get("contentId", "")
    if lvm.get("contentType") != "LOCKUP_CONTENT_TYPE_PLAYLIST" or not playlist_id:
        return None
    title = lvm.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")
    thumb = lvm.get("contentImage", {}).get("collectionThumbnailViewModel", {}).get("primaryThumbnail", {})
    thumb = thumb.get("thumbnailViewModel", {})
    sources = thumb.get("image", {}).get("sources") or []
    count_text = _find_text(thumb.get("overlays", []), _VIDEO_COUNT)
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    return {
        "id": playlist_id,
        "title": title or playlist_id,
        "url": url,
        "webpage_url": url,
        "thumbnail": sources[-1].get("url", "") if sources else "",
        "playlist_count": _parse_view_count(count_text),
        "_type": "playlist",
        "_is_playlist": True,
        "_playlist_name": title or playlist_id,
    }


def _runs_text(node: dict | None) -> str:
    runs = (node or {}).get("runs") or []
    return "".join(r.get("text", "") for r in runs) or (node or {}).get("simpleText", "")


def _parse_playlist_video(item: dict) -> VideoEntry | None:
    """One ``playlistVideoRenderer`` of a playlist page as a video entry. [verify live]"""
    lvm = item.get("lockupViewModel")
    if lvm:  # the layout YouTube serves now: the uploader is the first metadata part, with the channel link
        if lvm.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            return None
        entry = _video_from_lockup(lvm)
        rows = (lvm.get("metadata", {}).get("lockupMetadataViewModel", {}).get("metadata", {})
                .get("contentMetadataViewModel", {}).get("metadataRows", []))
        part = next((p.get("text", {}) for r in rows for p in r.get("metadataParts", []) if p.get("text")), {})
        if entry and part.get("content"):
            entry["uploader"] = entry["channel"] = part["content"]
            taps = (run.get("onTap", {}).get("innertubeCommand", {}) for run in part.get("commandRuns", []))
            channel_id = next((tap.get("browseEndpoint", {}).get("browseId", "") for tap in taps), "")
            if channel_id.startswith("UC"):
                entry["channel_id"] = channel_id
                entry["channel_url"] = f"https://www.youtube.com/channel/{channel_id}"
        return entry
    pv = item.get("playlistVideoRenderer") or {}
    video_id = pv.get("videoId", "")
    if not video_id:
        return None
    byline = (pv.get("shortBylineText") or {}).get("runs") or [{}]
    channel_id = byline[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
    thumbs = pv.get("thumbnail", {}).get("thumbnails") or []
    duration = _parse_int(pv.get("lengthSeconds"))
    entry: VideoEntry = {
        "id": video_id,
        "title": _runs_text(pv.get("title")) or video_id,
        "uploader": byline[0].get("text", ""),
        "channel": byline[0].get("text", ""),
        "duration": duration,
        "thumbnail": thumbs[-1].get("url", "") if thumbs else "",
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_type": "url",
    }
    if channel_id.startswith("UC"):
        entry["channel_id"] = channel_id
        entry["channel_url"] = f"https://www.youtube.com/channel/{channel_id}"
    return entry


_JOINED = re.compile(r"^Joined\b", re.IGNORECASE)

_TAB_PARSERS: dict[str, Callable[[dict], Entry | None]] = {
    "videos": _parse_channel_video_item,
    "shorts": _parse_short_item,
    "live": _parse_channel_video_item,
    "playlists": _parse_playlist_item,
}


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
