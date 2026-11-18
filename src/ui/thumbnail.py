"""Thumbnail files: resolve/download a JPEG, validate it, render PIL half-block ANSI art."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from src import logger
from src.cache import CACHE_DIR, THUMB_DIR
from src.entries import Entry

RENDERED_DIR = CACHE_DIR / "rendered"


def _ensure_rendered_dir() -> None:
    try:
        RENDERED_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _rendered_cache_path(video_id: str, cols: int, rows: int, fmt: str) -> Path:
    return RENDERED_DIR / f"{video_id}_{cols}x{rows}_{fmt}.ansi"


def _thumb_path(video_id: str) -> Path:
    return THUMB_DIR / f"{video_id}.jpg"


def _resolve_local_thumb(video_id: str, entry: Entry) -> Path | None:
    """Find the thumbnail yt-dlp wrote next to a downloaded file and copy it into the cache."""
    own = entry.get("_thumb_path")  # the library index already knows the image next to the file
    if own and Path(own).exists():
        dest = _thumb_path(video_id)
        if dest.exists():
            return dest
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(own, dest)
            return dest
        except OSError:
            return Path(own)
    local_path = entry.get("_local_path")
    if not local_path:
        return None
    media = Path(local_path)
    if not media.exists():
        return None
    for ext in (".jpg", ".webp", ".png"):
        candidate = media.with_suffix(ext)
        if candidate.exists():
            dest = _thumb_path(video_id)
            if dest.exists():
                return dest
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(candidate), str(dest))
                return dest
            except OSError:
                return candidate
    return None


def download(video_id: str, url: str, *, insecure: bool = False) -> Path | None:
    """Download a thumbnail to the cache. Returns its path, or None if the download failed or is not an image."""
    if not url:
        return None
    dest = _thumb_path(video_id)
    if dest.exists():
        return dest
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.debug("Thumbnail cache dir create failed for %s: %s", video_id, exc)
        return None
    try:
        from src.plat import download_thumbnail
        if download_thumbnail(url, str(dest), insecure=insecure):
            if validate_thumb(dest):
                logger.debug("Downloaded thumbnail for %s", video_id)
                return dest
            logger.debug("Thumbnail for %s is not a decodable image; dropped", video_id)
        dest.unlink(missing_ok=True)
        return None
    except Exception as exc:
        logger.debug("Thumbnail download error for %s: %s", video_id, exc)
        dest.unlink(missing_ok=True)
        return None


def ensure_thumb_jpeg(
    video_id: str, entry: Entry | None = None, *, url: str | None = None, insecure: bool = False
) -> Path | None:
    """Return a thumbnail path: disk cache, then library sidecar, then download.

    Pass `url` for channel avatars, `entry` for video thumbnails.
    """
    local = _thumb_path(video_id)
    if local.exists():
        return local
    if entry:
        found = _resolve_local_thumb(video_id, entry)
        if found and found.exists():
            return found
    dl_url = url or (best_thumb_url(entry) if entry else "")
    if dl_url:
        result = download(video_id, dl_url, insecure=insecure)
        if result and result.exists():
            return result
    return None


def validate_thumb(path: Path | None) -> bool:
    """Return True if PIL can fully decode the file."""
    if not path or not path.exists():
        return False
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(path) as img:
            img.load()
        return True
    except Exception:
        return False


def render_pil_halfblock(
    video_id: str,
    entry: Entry,
    *,
    cols: int = 38,
    rows: int = 20,
    insecure: bool = False,
) -> str:
    """Render 24-bit half-block ANSI art (two pixel rows per cell); "" if no image is available.

    Cached on disk per (video_id, cols, rows).
    """
    cache_path = _rendered_cache_path(video_id, cols, rows, "pil")
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding="utf-8")
        except OSError:
            pass

    local = _thumb_path(video_id)
    if not local.exists():
        local = _resolve_local_thumb(video_id, entry)
    if not local:
        url = best_thumb_url(entry)
        if not url:
            logger.debug("render_pil_halfblock: no URL for %s", video_id)
            return ""
        local = download(video_id, url, insecure=insecure)
    if not local or not local.exists():
        return ""

    try:
        from PIL import Image as _PILImage
        img = _PILImage.open(local).convert("RGB")
        img = img.resize((cols, rows * 2), _PILImage.LANCZOS)
        lines: list[str] = []
        for y in range(0, rows * 2, 2):
            row = ""
            for x in range(cols):
                r1, g1, b1 = img.getpixel((x, y))
                r2, g2, b2 = img.getpixel((x, y + 1))
                row += (
                    f"\x1b[38;2;{r1};{g1};{b1}m"
                    f"\x1b[48;2;{r2};{g2};{b2}m"
                    "\u2580"
                )
            lines.append(row + "\x1b[0m")
        ansi = "\n".join(lines)
    except Exception as exc:
        logger.debug("PIL halfblock render failed for %s: %s", video_id, exc)
        return ""

    _ensure_rendered_dir()
    try:
        cache_path.write_text(ansi, encoding="utf-8")
    except OSError:
        pass

    return ansi


_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_YTIMG_URL = "https://i.ytimg.com/vi/{}/mqdefault.jpg"


def best_thumb_url(entry: Entry) -> str:
    """Thumbnail URL for an entry: the extractor's choice, else derived from the video id.

    The derived URL needs no extraction, so rows that carry only an id (history,
    playlists, queue) still get a thumbnail.
    """
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        jpgs = [t for t in thumbs if "jpg" in t.get("url", "")]
        return (jpgs or thumbs)[-1].get("url", "")
    vid = entry.get("id", "")
    if _VIDEO_ID.fullmatch(vid) and not entry.get("_is_channel"):
        return _YTIMG_URL.format(vid)
    return ""


def prune_old_rendered(max_age_days: int = 7, max_count: int = 600) -> None:
    """Delete cached rendered ANSI files older than max_age_days, then cap to max_count."""
    if not RENDERED_DIR.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    files: list[tuple[float, Path]] = []
    deleted = 0
    for f in RENDERED_DIR.glob("*.ansi"):
        try:
            mtime = f.stat().st_mtime
            if mtime < cutoff:
                f.unlink(missing_ok=True)
                deleted += 1
            else:
                files.append((mtime, f))
        except OSError:
            pass
    capped = 0
    if len(files) > max_count:
        files.sort()
        for _, f in files[: len(files) - max_count]:
            f.unlink(missing_ok=True)
            capped += 1
    logger.debug("prune_old_rendered: %d expired, %d capped, %d kept",
                 deleted, capped, max(0, len(files) - capped))
