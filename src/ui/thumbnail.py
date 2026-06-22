"""Thumbnail rendering — download URL → render to ANSI terminal art.

Rendering pipeline:
  1. textual-image (Kitty TGP / Sixel) — pixel-perfect, handled by widget
  2. PIL half-block (pure Python) — 24-bit colored half-block characters
  3. Text placeholder — last resort

Rendered PIL output is cached on disk per (video_id, cols, rows) so that
re-rendering at the same panel size is essentially free.
"""

from __future__ import annotations
from pathlib import Path

from src.cache import CACHE_DIR, THUMB_DIR
from src import logger

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


# ── Download ───────────────────────────────────────────────────────────────────

def download(video_id: str, url: str) -> Path | None:
    """Download thumbnail to cache. Returns local path or None on failure."""
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
        if download_thumbnail(url, str(dest)):
            logger.debug("Downloaded thumbnail for %s", video_id)
            return dest
        dest.unlink(missing_ok=True)
        return None
    except Exception as exc:
        logger.debug("Thumbnail download error for %s: %s", video_id, exc)
        dest.unlink(missing_ok=True)
        return None


# ── PIL half-block renderer ───────────────────────────────────────────────────

def render_pil_halfblock(
    video_id: str,
    entry: dict,
    *,
    cols: int = 38,
    rows: int = 20,
) -> str:
    """Render thumbnail as 24-bit colored Unicode half-block art using Pillow.

    Each terminal cell covers 2 pixel rows: the upper half-block character
    is drawn with the top pixel as foreground color and the bottom pixel as
    background color, giving effectively double the vertical resolution.

    Works in any terminal supporting 24-bit ANSI color (iTerm2, WezTerm,
    Ghostty, Alacritty, Kitty, Windows Terminal, VS Code/Cursor, GNOME
    Terminal, etc.). Pillow is a hard dependency so this always works.

    Result is cached to RENDERED_DIR so re-renders at the same size are free.
    """
    cache_path = _rendered_cache_path(video_id, cols, rows, "pil")
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding="utf-8")
        except OSError:
            pass

    local = _thumb_path(video_id)
    if not local.exists():
        url = _best_thumb_url(entry)
        if not url:
            logger.debug("render_pil_halfblock: no URL for %s", video_id)
            return ""
        local = download(video_id, url) or Path("")

    if not local.exists():
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

    if ansi:
        _ensure_rendered_dir()
        try:
            cache_path.write_text(ansi, encoding="utf-8")
        except OSError:
            pass

    return ansi


# ── URL selection ──────────────────────────────────────────────────────────────

def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry."""
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        jpg_thumbs = [t for t in thumbs if "jpg" in t.get("url", "")]
        candidates = jpg_thumbs or thumbs
        best = candidates[-1] if candidates else thumbs[-1]
        return best.get("url", "")
    return ""


# ── Cache pruning ─────────────────────────────────────────────────────────────

def prune_old_rendered(max_age_days: int = 7, max_count: int = 600) -> None:
    """Delete cached rendered ANSI files older than max_age_days, then cap to max_count."""
    if not RENDERED_DIR.exists():
        return
    import time as _time
    cutoff = _time.time() - max_age_days * 86400
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
