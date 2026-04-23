"""Thumbnail rendering via chafa — download URL → render to ANSI terminal art."""

from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

from src.cache import THUMB_DIR
from src import logger


def _has_chafa() -> bool:
    return shutil.which("chafa") is not None


def _thumb_path(video_id: str) -> Path:
    return THUMB_DIR / f"{video_id}.jpg"


def download(video_id: str, url: str) -> Path | None:
    """Download thumbnail to cache using curl. Returns local path or None on failure."""
    if not url:
        return None
    dest = _thumb_path(video_id)
    if dest.exists():
        return dest
    # Use curl — avoids SSL cert issues in conda envs
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "8", "-o", str(dest), url],
            capture_output=True,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 100:
            logger.debug("Downloaded thumbnail for %s", video_id)
            return dest
        # Clean up failed/empty file
        dest.unlink(missing_ok=True)
        logger.debug("Thumbnail download failed for %s (curl rc=%d)", video_id, result.returncode)
        return None
    except Exception as exc:
        logger.debug("Thumbnail download error for %s: %s", video_id, exc)
        dest.unlink(missing_ok=True)
        return None


def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry."""
    # First try the pre-normalised 'thumbnail' field (set by ytdlp._normalise_entry)
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    # Fall back to scanning 'thumbnails' list
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        jpg_thumbs = [t for t in thumbs if "jpg" in t.get("url", "")]
        candidates = jpg_thumbs or thumbs
        best = candidates[-1] if candidates else thumbs[-1]
        return best.get("url", "")
    return ""


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
            logger.debug("No thumbnail URL for %s", video_id)
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
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("chafa render error for %s: %s", video_id, exc)
        return ""


def render_url(url: str, *, cols: int = 38, rows: int = 20) -> str:
    """Render a thumbnail from a URL directly (no caching). Used in preview."""
    if not _has_chafa() or not url:
        return ""
    try:
        # Pipe curl into chafa
        curl = subprocess.Popen(
            ["curl", "-sL", "--max-time", "8", url],
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
            timeout=10,
        )
        curl.wait()
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
