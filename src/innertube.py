"""YouTube InnerTube API client — lightweight, stdlib-only metadata fetching.

Provides near-instant (~220ms) video metadata without spawning yt-dlp subprocesses.
Uses YouTube's internal /player and /next API endpoints via simple HTTP POST.

This module has NO external dependencies beyond Python stdlib (json, urllib.request).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from src import logger

_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
_NEXT_URL = "https://www.youtube.com/youtubei/v1/next?prettyPrint=false"

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
    {id, title, description, view_count, upload_date, channel, channel_id,
     channel_url, uploader, uploader_id, duration, categories, is_live, keywords}

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
        logger.debug("innertube: no videoDetails for %s", video_id)
        return None

    mf = data.get("microformat", {}).get("playerMicroformatRenderer", {})

    upload_date = mf.get("uploadDate") or mf.get("publishDate")
    if upload_date and "T" in upload_date:
        upload_date = upload_date.split("T")[0]

    return {
        "id": video_id,
        "title": vd.get("title", ""),
        "description": vd.get("shortDescription", ""),
        "view_count": _parse_int(vd.get("viewCount")),
        "upload_date": upload_date,
        "channel": vd.get("author", ""),
        "channel_id": vd.get("channelId", ""),
        "channel_url": f"https://www.youtube.com/channel/{vd.get('channelId', '')}",
        "uploader": vd.get("author", ""),
        "uploader_id": "",
        "uploader_url": "",
        "duration": _parse_int(vd.get("lengthSeconds")),
        "categories": [mf.get("category", "")] if mf.get("category") else [],
        "is_live": vd.get("isLiveContent", False),
        "keywords": vd.get("keywords", []),
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_innertube": True,
    }


def fetch_engagement(video_id: str, *, timeout: int = 10) -> dict | None:
    """Fetch like/comment counts via InnerTube /next API (~1s).

    Returns {like_count: int|None, comment_count: int|None} or None on failure.
    This is a heavier call (~1s) — use only after extended dwell.
    """
    payload = {
        "videoId": video_id,
        "context": _WEB_CONTEXT,
    }

    data = _post_json(_NEXT_URL, payload, timeout=timeout)
    if not data:
        return None

    text = json.dumps(data)

    like_count = None
    # Try direct likeCount field first
    like_match = re.search(r'"likeCount"[:\s]+"?(\d+)"?', text)
    if like_match:
        like_count = int(like_match.group(1))
    else:
        # Fall back to accessibility text: "like this video along with 19,162,368 other people"
        acc_match = re.search(r'"like this video along with ([\d,]+)', text)
        if acc_match:
            like_count = int(acc_match.group(1).replace(",", ""))

    comment_count = None
    # Try "commentCount":{"simpleText":"123"} or "countText":{"runs":[{"text":"123"}]}
    comment_match = re.search(r'"commentCount":\{"simpleText":"([^"]+)"', text)
    if not comment_match:
        comment_match = re.search(r'Comments\n([\d,]+)', text)
    if comment_match:
        raw = comment_match.group(1).replace(",", "")
        try:
            comment_count = int(raw)
        except ValueError:
            pass

    return {"like_count": like_count, "comment_count": comment_count}


def _parse_int(value) -> int | None:
    """Safely parse a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
