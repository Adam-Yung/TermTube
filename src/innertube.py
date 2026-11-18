"""YouTube InnerTube client: stdlib-only video metadata (~220 ms) and channel browse."""

from __future__ import annotations

import http.client
import json
import re
import threading
import urllib.parse
from collections.abc import Callable
from typing import Any

from src import logger
from src.entries import PlaylistEntry, VideoEntry

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


def _post_json(url: str, payload: dict, *, timeout: int = 8) -> dict | None:
    """POST JSON; the parsed response, or None on any error."""
    parts = urllib.parse.urlsplit(url)
    path = f"{parts.path}?{parts.query}" if parts.query else parts.path
    reply = _request("POST", parts.netloc, path, body=json.dumps(payload).encode(), headers=_HEADERS, timeout=timeout)
    if reply is None:
        return None
    status, data = reply
    endpoint = parts.path.rsplit("/", 1)[-1]
    if status != 200:
        logger.debug("innertube POST %s: HTTP %s", endpoint, status)
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        logger.debug("innertube POST %s: bad JSON: %s", endpoint, exc)
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


# Base64 protobuf tab selector for the Videos tab, newest first.
_CHANNEL_VIDEOS_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"


def fetch_channel_videos(channel_id: str, *, timeout: int = 12) -> list[VideoEntry]:
    """Newest-first channel video entries from the /browse API (~600 ms for 30). Empty on failure."""
    payload = {
        "browseId": channel_id,
        "params": _CHANNEL_VIDEOS_PARAMS,
        "context": _WEB_CONTEXT,
    }

    data = _post_json(_BROWSE_URL, payload, timeout=timeout)
    if not data:
        return []

    entries: list[VideoEntry] = []
    try:
        tabs = (data.get("contents", {})
                .get("twoColumnBrowseResultsRenderer", {})
                .get("tabs", []))

        for tab in tabs:
            tr = tab.get("tabRenderer", {})
            if not tr.get("selected"):
                continue
            items = (tr.get("content", {})
                     .get("richGridRenderer", {})
                     .get("contents", []))
            for item in items:
                entry = _parse_channel_video_item(item)
                if entry:
                    entries.append(entry)
            break
    except (KeyError, TypeError, AttributeError) as exc:
        logger.debug("innertube browse parse error: %s", exc)

    logger.debug("innertube: fetched %d channel videos for %s", len(entries), channel_id)
    return entries


def _parse_channel_video_item(item: dict) -> VideoEntry | None:
    """One /browse richGridRenderer item as a video entry, or None if it is not a video."""
    ri = item.get("richItemRenderer", {})
    if not ri:
        return None

    lvm = ri.get("content", {}).get("lockupViewModel", {})
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
            if "view" in text.lower():
                view_count_text = text
            elif "ago" in text.lower() or "streamed" in text.lower():
                published_text = text

    duration_text = ""
    overlays = (lvm.get("contentImage", {})
                .get("thumbnailViewModel", {})
                .get("overlays", []))
    for ov in overlays:
        tbov = ov.get("thumbnailBottomOverlayViewModel", {})
        if tbov:
            for badge in tbov.get("badges", []):
                bvm = badge.get("thumbnailBadgeViewModel", {})
                text = bvm.get("text", "")
                if text and ":" in text:
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

    return {
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


# Base64 protobuf tab selector for the Playlists tab.
_CHANNEL_PLAYLISTS_PARAMS = "EglwbGF5bGlzdHPyBgQKAkIA"
_MAX_PLAYLIST_PAGES = 4
_VIDEO_COUNT = re.compile(r"^[\d,]+ videos?$")

_SEARCH_URL = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
_RESOLVE_URL = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
_MAX_SEARCH_PAGES = 4


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


def _search_items(sections: list[dict]) -> tuple[list[VideoEntry], str]:
    """Video entries and the next continuation token from a list of result sections."""
    entries: list[VideoEntry] = []
    token = ""
    for section in sections:
        for item in section.get("itemSectionRenderer", {}).get("contents", []):
            entry = _parse_search_video(item.get("videoRenderer", {}))
            if entry:
                entries.append(entry)
        cont = section.get("continuationItemRenderer", {})
        token = cont.get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", token)
    return entries, token


def search_videos(
    query: str,
    *,
    count: int = 50,
    skip_ids: set[str] | None = None,
    on_first_batch: Callable[[list[VideoEntry]], None] | None = None,
) -> list[VideoEntry]:
    """Video results for ``query`` through InnerTube ``/search``. Anonymous. Empty on any failure.

    Follows continuation tokens until ``count`` videos are collected or ``_MAX_SEARCH_PAGES`` pages are read.
    ``on_first_batch`` receives the first page's videos as soon as that page arrives.
    """
    skip_ids = skip_ids or set()
    payload: dict = {"query": query, "context": _WEB_CONTEXT}
    results: list[VideoEntry] = []
    seen = set(skip_ids)
    for _ in range(_MAX_SEARCH_PAGES):
        data = _post_json(_SEARCH_URL, payload)
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
    match = re.search(r"/channel/(UC[\w-]{22})", channel_url)
    if match:
        return match.group(1)
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
    }


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


def _playlist_page(data: dict) -> tuple[list[PlaylistEntry], str]:
    """Playlist entries and the next continuation token from a Playlists-tab or continuation response."""
    actions = data.get("onResponseReceivedActions")
    if actions:
        items = actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
    else:
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        selected = next((t["tabRenderer"] for t in tabs if t.get("tabRenderer", {}).get("selected")), {})
        sections = selected.get("content", {}).get("sectionListRenderer", {}).get("contents", [])
        items = [i for s in sections for c in s.get("itemSectionRenderer", {}).get("contents", [])
                 for i in c.get("gridRenderer", {}).get("items", [])]
    entries = [e for e in map(_parse_playlist_item, items) if e]
    token = next((i["continuationItemRenderer"].get("continuationEndpoint", {}).get("continuationCommand", {})
                  .get("token", "") for i in items if "continuationItemRenderer" in i), "")
    return entries, token


def fetch_channel_playlists(channel_id: str, *, count: int = 80, timeout: int = 12) -> list[PlaylistEntry]:
    """Playlists of a channel from /browse, following continuations up to ``count``. Anonymous. Empty on failure."""
    payload: dict = {"browseId": channel_id, "params": _CHANNEL_PLAYLISTS_PARAMS, "context": _WEB_CONTEXT}
    entries: list[PlaylistEntry] = []
    for _ in range(_MAX_PLAYLIST_PAGES):
        data = _post_json(_BROWSE_URL, payload, timeout=timeout)
        if not data:
            break
        page, token = _playlist_page(data)
        entries.extend(page)
        if len(entries) >= count or not token:
            break
        payload = {"continuation": token, "context": _WEB_CONTEXT}
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
