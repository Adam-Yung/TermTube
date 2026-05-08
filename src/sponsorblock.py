"""TermTube v2 — SponsorBlock segment fetcher.

Fetches sponsor/selfpromo segments for a video from the SponsorBlock
public API (https://sponsor.ajay.app).  No account required.

Results are cached in ~/.cache/termtube/sb/{video_id}.json.
Returns [] gracefully on any network or parse error.

MUST be called from a worker thread.
"""
from __future__ import annotations

from typing import TypedDict

import httpx

import cache as _cache
import logger


class Segment(TypedDict):
    start: float
    end: float
    category: str


_API_BASE = "https://sponsor.ajay.app/api/skipSegments"

# Category → display color (for ProgressBar ticks)
CATEGORY_COLORS: dict[str, str] = {
    "sponsor":       "#00cc00",
    "selfpromo":     "#ffff00",
    "interaction":   "#cc00ff",
    "intro":         "#00ffff",
    "outro":         "#0000ff",
    "preview":       "#ff6600",
    "music_offtopic":"#ff0000",
    "filler":        "#7f7f7f",
    "poi_highlight": "#ff00ff",
}


def fetch_segments(
    video_id: str,
    categories: list[str] | None = None,
    ttl: int = 3600,
) -> list[Segment]:
    """Return SponsorBlock segments for *video_id*.

    Checks the disk cache first.  Fetches from network on miss.
    """
    cats = categories or ["sponsor", "selfpromo"]

    cached = _cache.get_sb(video_id, ttl=ttl)
    if cached is not None:
        return [s for s in cached if s.get("category") in cats]

    try:
        params = {
            "videoID": video_id,
            "categories": str(cats).replace("'", '"'),
        }
        resp = httpx.get(_API_BASE, params=params, timeout=8.0)
        if resp.status_code == 404:
            # No segments exist for this video
            _cache.put_sb(video_id, [])
            return []
        resp.raise_for_status()
        raw = resp.json()
        segments: list[Segment] = []
        for item in raw:
            seg = item.get("segment", [])
            if len(seg) == 2:
                segments.append(Segment(
                    start=float(seg[0]),
                    end=float(seg[1]),
                    category=item.get("category", "sponsor"),
                ))
        _cache.put_sb(video_id, segments)
        return [s for s in segments if s.get("category") in cats]
    except httpx.HTTPStatusError as exc:
        logger.debug("SponsorBlock HTTP error %s: %s", video_id, exc)
    except Exception as exc:
        logger.debug("SponsorBlock error %s: %s", video_id, exc)

    return []
