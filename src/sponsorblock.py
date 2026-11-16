"""SponsorBlock segment client with a 24 h disk cache."""

from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src import logger
from src.plat import get_cache_dir

_UA_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()

_API_BASE = "https://sponsor.ajay.app/api/skipSegments"
_CACHE_DIR = get_cache_dir() / "sb"
_CACHE_TTL = 86400
_REQUEST_TIMEOUT = 3.0
_SSL_PREF_PATH = get_cache_dir() / "ssl_pref"


_ssl_context: ssl.SSLContext | None = None


def _build_ssl_context(pref: str) -> ssl.SSLContext:
    if pref == "certifi":
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    if pref == "system":
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _read_ssl_pref() -> str | None:
    try:
        if _SSL_PREF_PATH.exists():
            pref = _SSL_PREF_PATH.read_text(encoding="utf-8").strip()
            if pref in ("certifi", "system", "unverified"):
                return pref
    except OSError:
        pass
    return None


def _write_ssl_pref(pref: str) -> None:
    try:
        _SSL_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SSL_PREF_PATH.write_text(pref, encoding="utf-8")
    except OSError:
        pass


def _invalidate_ssl_pref() -> None:
    """Forget the SSL preference (memory and disk) so the next request re-probes."""
    global _ssl_context
    _ssl_context = None
    try:
        _SSL_PREF_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _get_ssl_context() -> ssl.SSLContext:
    """SSL context from the disk-cached preference, else the first of certifi, system, unverified that builds.

    Probing only creates contexts; it makes no network call.
    """
    pref = _read_ssl_pref()
    if pref:
        try:
            return _build_ssl_context(pref)
        except Exception:
            pass  # e.g. certifi uninstalled since the preference was written

    for candidate in ("certifi", "system"):
        try:
            ctx = _build_ssl_context(candidate)
        except Exception:
            continue
        _write_ssl_pref(candidate)
        return ctx
    _write_ssl_pref("unverified")
    return _build_ssl_context("unverified")


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
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Segment(start=s["start"], end=s["end"], category=s["category"]) for s in raw]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _write_cache(video_id: str, segments: list[Segment]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [{"start": s.start, "end": s.end, "category": s.category} for s in segments]
        _cache_path(video_id).write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _do_fetch(url: str, ctx: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"TermTube/{_UA_VERSION}"})
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT, context=ctx) as resp:
        return resp.read()


def _request(url: str) -> bytes:
    """GET ``url``; one retry with a re-probed SSL context if the cached preference fails."""
    try:
        return _do_fetch(url, _cached_ssl_context())
    except ssl.SSLError:
        logger.debug("SponsorBlock: SSL error with cached pref, re-probing")
        _invalidate_ssl_pref()
        return _do_fetch(url, _cached_ssl_context())


def fetch_segments(video_id: str, categories: list[str] | None = None) -> list[Segment]:
    """Segments for a video, sorted by start; empty on any failure. Safe in a worker thread.

    Failures are cached as empty for the TTL so a bad video is not re-requested.
    """
    if not video_id:
        return []

    cached = _read_cache(video_id)
    if cached is not None:
        return cached

    cats_param = json.dumps(categories or ["sponsor", "selfpromo"], separators=(",", ":"))
    url = f"{_API_BASE}?videoID={video_id}&categories={cats_param}"
    logger.debug("SponsorBlock fetch: %s", url)

    try:
        raw = _request(url)
    except OSError as exc:
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


def fetch_segments_async(
    video_id: str,
    categories: list[str],
    on_done: Callable[[list[Segment]], None],
) -> threading.Thread:
    """Fetch segments on a daemon thread and pass them, sorted by start, to ``on_done``."""

    def run() -> None:
        on_done(fetch_segments(video_id, categories))

    thread = threading.Thread(target=run, daemon=True, name="sponsorblock")
    thread.start()
    return thread
