"""SponsorBlock API client with disk caching."""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from src import logger
from src.platform import get_cache_dir

_UA_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()

_API_BASE = "https://sponsor.ajay.app/api/skipSegments"
_CACHE_DIR = get_cache_dir() / "sb"
_CACHE_TTL = 86400  # 24 hours
_REQUEST_TIMEOUT = 3.0


def _get_ssl_context() -> ssl.SSLContext:
    """Build an SSL context, falling back gracefully on certificate issues.

    Tries in order:
    1. certifi bundle (most portable)
    2. System default certs
    3. Unverified context (still encrypted, no cert validation -- for proxies)
    """
    # Try certifi first
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        # Quick probe to validate cert chain works
        urllib.request.urlopen(
            urllib.request.Request(f"{_API_BASE}/../", method="HEAD"),
            timeout=2, context=ctx
        )
        return ctx
    except Exception:
        pass

    # Try system defaults
    try:
        ctx = ssl.create_default_context()
        urllib.request.urlopen(
            urllib.request.Request(f"{_API_BASE}/../", method="HEAD"),
            timeout=2, context=ctx
        )
        return ctx
    except Exception:
        pass

    # Last resort: unverified context (still encrypted, just no cert validation)
    logger.debug("SponsorBlock: falling back to unverified SSL (proxy detected)")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# Cache the context so we only probe once per process
_ssl_context: ssl.SSLContext | None = None


def _cached_ssl_context() -> ssl.SSLContext:
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = _get_ssl_context()
    return _ssl_context


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
        req = urllib.request.Request(url, headers={"User-Agent": f"TermTube/{_UA_VERSION}"})
        ctx = _cached_ssl_context()
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT, context=ctx) as resp:
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
