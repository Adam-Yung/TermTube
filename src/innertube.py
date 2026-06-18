"""YouTube InnerTube API client — lightweight, stdlib-only metadata fetching.

Provides near-instant (~220ms) video metadata without spawning yt-dlp subprocesses.
Uses YouTube's internal /player API endpoint via a single HTTP POST.

This module has NO external dependencies beyond Python stdlib (json, urllib.request).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from src import logger

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


def _post_json(url: str, payload: dict, *, timeout: int = 8) -> dict | None:
    """POST JSON to a YouTube API endpoint. Returns parsed response or None."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        logger.debug("innertube POST failed (%s): %s", url.split("/")[-1], exc)
        return None


def fetch_video_details(video_id: str, *, timeout: int = 8) -> dict | None:
    """Fetch video metadata via InnerTube /player API (~220ms).

    Returns a normalized dict compatible with the cache/detail panel format:
    {id, title, description, view_count, like_count, upload_date, channel,
     channel_id, channel_url, uploader, uploader_id, uploader_url, duration,
     categories, is_live, keywords}

    Returns None on failure (network error, invalid video, etc.).
    """
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

    # Normalize upload_date to YYYYMMDD compact format (yt-dlp convention)
    upload_date = mf.get("uploadDate") or mf.get("publishDate")
    if upload_date and "T" in upload_date:
        upload_date = upload_date.split("T")[0]
    if upload_date:
        upload_date = upload_date.replace("-", "")

    # Extract @handle from ownerProfileUrl (e.g. "http://www.youtube.com/@RickAstleyYT")
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



# ── Channel video params (protobuf-encoded tab selectors) ─────────────────────
# These are base64-encoded protobuf values that select the Videos tab with sort.
_CHANNEL_VIDEOS_DATE = "EgZ2aWRlb3PyBgQKAjoA"      # Videos tab, sorted by date (newest)
_CHANNEL_VIDEOS_POPULAR = "EgZ2aWRlb3PyBgQKAjoA"   # Videos tab (popular sort not reliably supported; falls back to date)


def fetch_channel_videos(
    channel_id: str,
    *,
    sort: str = "date",
    timeout: int = 12,
) -> list[dict]:
    """Fetch channel videos via InnerTube /browse API (~600ms for 30 videos).

    Returns a list of normalized video entry dicts compatible with the video list.
    sort: "date" (newest first) or "views" (most popular first).

    Returns empty list on failure.
    """
    params = _CHANNEL_VIDEOS_POPULAR if sort == "views" else _CHANNEL_VIDEOS_DATE

    payload = {
        "browseId": channel_id,
        "params": params,
        "context": _WEB_CONTEXT,
    }

    data = _post_json(_BROWSE_URL, payload, timeout=timeout)
    if not data:
        return []

    # Navigate response structure to find video items
    entries: list[dict] = []
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


def _parse_channel_video_item(item: dict) -> dict | None:
    """Parse a single video item from the /browse richGridRenderer response."""
    ri = item.get("richItemRenderer", {})
    if not ri:
        return None

    lvm = ri.get("content", {}).get("lockupViewModel", {})
    if not lvm:
        return None

    video_id = lvm.get("contentId", "")
    if not video_id:
        return None

    # Extract metadata
    meta = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = meta.get("title", {}).get("content", "")

    # Extract views and relative date from metadata rows
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

    # Extract duration from overlay badges
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

    # Extract thumbnail
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
    import re
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
