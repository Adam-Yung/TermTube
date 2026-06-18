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


def _parse_int(value) -> int | None:
    """Safely parse a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
