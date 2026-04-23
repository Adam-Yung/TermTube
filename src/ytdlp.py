"""yt-dlp interface — all yt-dlp subprocess calls live here.

Progressive streaming design:
  stream_flat()  →  yields entry dicts as yt-dlp produces them (fast, no blocking)
  fetch_full()   →  fetches complete metadata for one video (slower, use async)
"""

from __future__ import annotations
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Generator, Iterable

from src.cache import Cache
from src import logger

# ── Feed URLs ─────────────────────────────────────────────────────────────────

FEED_URLS = {
    "home":          "https://www.youtube.com/feed/recommended",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}

# ── Flags that make flat-playlist fetches fast ────────────────────────────────
_FAST_FLAGS = [
    "--flat-playlist",
    "--dump-json",
    "--no-warnings",
    "--quiet",
    "--extractor-args", "youtube:skip=dash,hls",
    "--no-playlist-reverse",
]


# ── Cookie helper ─────────────────────────────────────────────────────────────

def cookie_args(config) -> list[str]:
    """Return yt-dlp --cookies or --cookies-from-browser flags."""
    return config.cookie_args  # delegated to Config


# ── Thumbnail normalisation ───────────────────────────────────────────────────

def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry dict."""
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        # Prefer jpg; yt-dlp lists lowest→highest resolution
        jpg = [t for t in thumbs if "jpg" in t.get("url", "")]
        best = (jpg or thumbs)[-1]
        return best.get("url", "")
    return entry.get("thumbnail", "")


def _normalise_entry(entry: dict) -> dict:
    """Ensure flat-playlist entries have a 'thumbnail' field and webpage_url."""
    entry.setdefault("webpage_url", f"https://www.youtube.com/watch?v={entry.get('id', '')}")
    # Flat entries may only have 'thumbnails' list — promote the best to 'thumbnail'
    if not entry.get("thumbnail"):
        url = _best_thumb_url(entry)
        if url:
            entry["thumbnail"] = url
    return entry


# ── Low-level streaming ───────────────────────────────────────────────────────

def _stream_json_lines(cmd: list[str], *, capture_stderr: bool = False) -> Generator[dict, None, None]:
    """Run cmd, yield each stdout line parsed as JSON. Ignores non-JSON lines."""
    logger.debug("yt-dlp cmd: %s", " ".join(cmd))
    try:
        stderr_dest = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_dest,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
        proc.wait()
        if capture_stderr and proc.stderr:
            err = proc.stderr.read()
            if err.strip():
                logger.debug("yt-dlp stderr: %s", err.strip())
            if proc.returncode != 0:
                logger.warning("yt-dlp exited %d: %s", proc.returncode, err.strip())
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Install with: brew install yt-dlp")


# ── Public streaming API ──────────────────────────────────────────────────────

def stream_flat(
    url: str,
    config,
    cache: Cache,
    *,
    on_entry: Callable[[dict], None] | None = None,
) -> Generator[dict, None, None]:
    """
    Stream basic video entries from a URL using --flat-playlist.
    Each entry is written to cache as it arrives.
    Yields entry dicts; also calls on_entry(entry) if provided.
    """
    cmd = ["yt-dlp", *_FAST_FLAGS, *cookie_args(config), url]
    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        _normalise_entry(entry)
        cache.put_video(entry)
        if on_entry:
            on_entry(entry)
        yield entry


def stream_search(
    query: str,
    config,
    cache: Cache,
    *,
    count: int = 40,
) -> Generator[dict, None, None]:
    """Stream search results for query."""
    url = f"ytsearch{count}:{query}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--flat-playlist",
        "--extractor-args", "youtube:skip=dash,hls",
        *cookie_args(config),
        url,
    ]
    for entry in _stream_json_lines(cmd, capture_stderr=logger.is_debug()):
        _normalise_entry(entry)
        cache.put_video(entry)
        yield entry


# ── Full metadata (for video detail page) ────────────────────────────────────

def fetch_full(video_id: str, config, cache: Cache) -> dict | None:
    """Fetch complete metadata for a single video. Returns cached if fresh."""
    cached = cache.get_video(video_id)
    if cached and cached.get("description") is not None:
        logger.debug("fetch_full cache hit: %s", video_id)
        return cached

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--skip-download",
        "--extractor-args", "youtube:skip=dash,hls",
        *cookie_args(config),
        url,
    ]
    logger.debug("fetch_full fetching: %s", video_id)
    results = list(_stream_json_lines(cmd, capture_stderr=logger.is_debug()))
    if not results:
        logger.warning("fetch_full got no data for %s — using flat cache", video_id)
        return cache.get_video_raw(video_id)  # fall back to flat data
    entry = results[0]
    _normalise_entry(entry)
    cache.put_video(entry)
    return entry


def enrich_in_background(
    video_ids: Iterable[str],
    config,
    cache: Cache,
    *,
    max_workers: int = 2,
    on_done: Callable[[str, dict], None] | None = None,
) -> None:
    """
    Fetch full metadata for a list of video IDs in parallel background threads.
    on_done(video_id, entry) is called when each finishes.
    Runs as a daemon thread — fire and forget.
    """
    ids = list(video_ids)
    if not ids:
        return

    logger.debug("enrich_in_background: %d videos, max_workers=%d", len(ids), max_workers)

    def _worker() -> None:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fetch_full, vid, config, cache): vid for vid in ids}
            for future in as_completed(futures):
                vid = futures[future]
                try:
                    entry = future.result()
                    if entry and on_done:
                        on_done(vid, entry)
                except Exception as exc:
                    logger.debug("enrich_in_background error for %s: %s", vid, exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ── Download ──────────────────────────────────────────────────────────────────

def download_video(video_id: str, config, *, on_progress: Callable[[str], None] | None = None) -> bool:
    """Download video to config.video_dir. Returns True on success."""
    config.video_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"

    quality = config.preferred_quality
    fmt = "bestvideo+bestaudio/best" if quality == "best" else f"bestvideo[height<={quality}]+bestaudio/best"

    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", str(config.video_dir / config.video_format),
        "--write-info-json",
        "--write-thumbnail",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    logger.debug("download_video: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def download_audio(video_id: str, config, *, on_progress: Callable[[str], None] | None = None) -> bool:
    """Download audio-only to config.audio_dir. Returns True on success."""
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        "yt-dlp",
        "--format", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", str(config.audio_dir / config.audio_format),
        "--write-info-json",
        "--write-thumbnail",
        "--no-warnings",
        *cookie_args(config),
        url,
    ]
    logger.debug("download_audio: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def get_stream_url(video_id: str, config, *, audio_only: bool = False) -> str | None:
    """Get a direct streamable URL for mpv (avoids re-fetching inside mpv)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    fmt = "bestaudio/best" if audio_only else "bestvideo+bestaudio/best"
    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--get-url",
        "--no-warnings",
        "--quiet",
        *cookie_args(config),
        url,
    ]
    logger.debug("get_stream_url: %s", url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[0]
    logger.warning("get_stream_url failed for %s: %s", video_id, result.stderr.strip())
    return None


def open_in_browser(video_id: str) -> None:
    """Open the video in the default system browser."""
    import webbrowser
    webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")


def subscribe_channel(channel_url: str, config) -> bool:
    """Subscribe to a channel (requires authenticated session)."""
    # yt-dlp doesn't support subscribing; open in browser instead
    import webbrowser
    webbrowser.open(channel_url)
    return True
