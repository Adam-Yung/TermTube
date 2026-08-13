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
from src.plat import get_cache_dir

_UA_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()

_API_BASE = "https://sponsor.ajay.app/api/skipSegments"
_CACHE_DIR = get_cache_dir() / "sb"
_CACHE_TTL = 86400  # 24 hours
_REQUEST_TIMEOUT = 3.0
_SSL_PREF_PATH = get_cache_dir() / "ssl_pref"


def _build_ssl_context(pref: str) -> ssl.SSLContext:
    """Build an SSL context for a given preference string."""
    if pref == "certifi":
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    elif pref == "system":
        return ssl.create_default_context()
    else:  # "unverified"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


def _read_ssl_pref() -> str | None:
    """Read cached SSL preference from disk."""
    try:
        if _SSL_PREF_PATH.exists():
            pref = _SSL_PREF_PATH.read_text().strip()
            if pref in ("certifi", "system", "unverified"):
                return pref
    except OSError:
        pass
    return None


def _write_ssl_pref(pref: str) -> None:
    """Persist SSL preference to disk."""
    try:
        _SSL_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SSL_PREF_PATH.write_text(pref)
    except OSError:
        pass


def _invalidate_ssl_pref() -> None:
    """Remove cached SSL preference so it will be re-probed."""
    global _ssl_context
    _ssl_context = None
    try:
        _SSL_PREF_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _get_ssl_context() -> ssl.SSLContext:
    """Build an SSL context, using disk-cached preference to skip probing.

    On first use, tries certifi -> system -> unverified and caches whichever
    works. Subsequent cold starts read the preference from disk.
    """
    pref = _read_ssl_pref()
    if pref:
        try:
            return _build_ssl_context(pref)
        except Exception:
            pass  # preference invalid (e.g. certifi uninstalled), re-probe

    # Probe in priority order (no network calls -- just context creation)
    for candidate in ("certifi", "system", "unverified"):
        try:
            ctx = _build_ssl_context(candidate)
            _write_ssl_pref(candidate)
            return ctx
        except Exception:
            continue

    # Should never reach here, but unverified always succeeds
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


def _do_fetch(url: str, ctx: ssl.SSLContext) -> bytes:
    """Perform the actual HTTP request. Raises on SSL or network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": f"TermTube/{_UA_VERSION}"})
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT, context=ctx) as resp:
        return resp.read()


def fetch_segments(video_id: str, categories: list[str] | None = None) -> list[Segment]:
    """Fetch SponsorBlock segments for a video. Safe to call from a worker thread.

    Returns an empty list on network error, timeout, or if no segments exist.
    If the cached SSL preference causes an SSLError, invalidates it and retries.
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
        ctx = _cached_ssl_context()
        raw = _do_fetch(url, ctx)
    except ssl.SSLError:
        logger.debug("SponsorBlock: SSL error with cached pref, re-probing")
        _invalidate_ssl_pref()
        try:
            ctx = _cached_ssl_context()
            raw = _do_fetch(url, ctx)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            logger.debug("SponsorBlock fetch failed for %s: %s", video_id, exc)
            _write_cache(video_id, [])
            return []
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.debug("SponsorBlock fetch failed for %s: %s", video_id, exc)
        _write_cache(video_id, [])
        return []

    try:
        data = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
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
