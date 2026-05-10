"""SponsorBlock API client with disk caching."""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from src import logger

_API_BASE = "https://sponsor.ajay.app/api/skipSegments"
_CACHE_DIR = Path.home() / ".cache" / "termtube" / "sb"
_CACHE_TTL = 86400  # 24 hours
_REQUEST_TIMEOUT = 3.0


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    category: str


def _cache_path(video_id: str) -> Path:
    return _CACHE_DIR / f"{video_id}.json"


def _read_cache(video_id: str) -> list[Segment] | None:
    path = _cache_path(video_id)
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        if time.time() - mtime > _CACHE_TTL:
            path.unlink(missing_ok=True)
            return None
        raw = json.loads(path.read_text())
        return [Segment(start=s["start"], end=s["end"], category=s["category"]) for s in raw]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _write_cache(video_id: str, segments: list[Segment]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [{"start": s.start, "end": s.end, "category": s.category} for s in segments]
        _cache_path(video_id).write_text(json.dumps(data))
    except OSError:
        pass


def fetch_segments(video_id: str, categories: list[str] | None = None) -> list[Segment]:
    """Fetch SponsorBlock segments for a video. Safe to call from a worker thread.

    Returns an empty list on network error, timeout, or if no segments exist.
    """
    if not video_id:
        return []

    cached = _read_cache(video_id)
    if cached is not None:
        return cached

    if categories is None:
        categories = ["sponsor", "selfpromo"]

    cats_param = json.dumps(categories, separators=(",", ":"))
    url = f"{_API_BASE}?videoID={video_id}&categories={cats_param}"

    logger.debug("SponsorBlock fetch: %s", url)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TermTube/0.2"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.debug("SponsorBlock fetch failed for %s: %s", video_id, exc)
        _write_cache(video_id, [])
        return []

    segments: list[Segment] = []
    for item in data:
        seg = item.get("segment")
        cat = item.get("category", "sponsor")
        if isinstance(seg, list) and len(seg) == 2:
            try:
                segments.append(Segment(start=float(seg[0]), end=float(seg[1]), category=cat))
            except (TypeError, ValueError):
                continue

    segments.sort(key=lambda s: s.start)
    _write_cache(video_id, segments)
    return segments
