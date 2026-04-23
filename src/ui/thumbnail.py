"""Thumbnail rendering via chafa — download URL → render to ANSI terminal art."""

from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

from src.cache import THUMB_DIR


def _has_chafa() -> bool:
    return shutil.which("chafa") is not None


def _thumb_path(video_id: str) -> Path:
    return THUMB_DIR / f"{video_id}.jpg"


def download(video_id: str, url: str) -> Path | None:
    """Download thumbnail to cache. Returns local path or None on failure."""
    if not url:
        return None
    dest = _thumb_path(video_id)
    if dest.exists():
        return dest
    try:
        import urllib.request
        urllib.request.urlretrieve(url, dest)
        return dest
    except Exception:
        return None


def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry."""
    # entry may have 'thumbnails' (list) or 'thumbnail' (str)
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        # Sort by preference (higher resolution first, but skip webp if jpg available)
        jpg_thumbs = [t for t in thumbs if "jpg" in t.get("url", "")]
        candidates = jpg_thumbs or thumbs
        # yt-dlp thumbnails are usually ordered lowest→highest resolution
        best = candidates[-1] if candidates else thumbs[-1]
        return best.get("url", "")
    return entry.get("thumbnail", "")


def render(video_id: str, entry: dict, *, cols: int = 38, rows: int = 20) -> str:
    """
    Return chafa ANSI output for the video's thumbnail.
    Downloads thumbnail if not cached. Returns empty string if unavailable.
    """
    if not _has_chafa():
        return ""

    local = _thumb_path(video_id)
    if not local.exists():
        url = _best_thumb_url(entry)
        if not url:
            return ""
        local = download(video_id, url) or Path("")

    if not local.exists():
        return ""

    try:
        result = subprocess.run(
            [
                "chafa",
                f"--size={cols}x{rows}",
                "--format=symbols",      # best cross-terminal compatibility
                "--optimize=9",
                "--stretch",
                str(local),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def render_url(url: str, *, cols: int = 38, rows: int = 20) -> str:
    """Render a thumbnail from a URL directly (no caching). Used in preview."""
    if not _has_chafa() or not url:
        return ""
    try:
        # Pipe curl into chafa
        curl = subprocess.Popen(
            ["curl", "-sL", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [
                "chafa",
                f"--size={cols}x{rows}",
                "--format=symbols",
                "--optimize=9",
                "--stretch",
                "-",   # read from stdin
            ],
            stdin=curl.stdout,
            capture_output=True,
            text=True,
            timeout=8,
        )
        curl.wait()
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
