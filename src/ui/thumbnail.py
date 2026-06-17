"""Thumbnail rendering via chafa — download URL → render to ANSI terminal art.

Supports both symbols mode (universal) and kitty graphics protocol
(high-quality images, auto-detected from KITTY_WINDOW_ID environment variable).

Rendered chafa output is cached on disk per (video_id, cols, rows) so that
re-rendering at the same panel size is essentially free.

On Windows, chafa is skipped entirely — textual-image handles rendering.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Callable

from src.cache import CACHE_DIR, THUMB_DIR
from src import logger
from src.platform import has_chafa as _platform_has_chafa, get_thumbnail_download_cmd, get_chafa_exe

CHAFA_DIR = CACHE_DIR / "chafa"


def _ensure_chafa_dir() -> None:
    try:
        CHAFA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _chafa_cache_path(video_id: str, cols: int, rows: int, fmt: str) -> Path:
    return CHAFA_DIR / f"{video_id}_{cols}x{rows}_{fmt}.ansi"



def _chafa_format_for_tui(config=None) -> str:
    """Return the chafa format to use inside the Textual TUI.

    Sixel (DCS sequences) and Kitty graphics (binary) are both incompatible
    with Textual's cell-based renderer:
      - Kitty: binary data → Rich.Text.from_ansi() shows raw bytes.
      - Sixel: Rich only parses CSI sequences (ESC [). DCS sequences (ESC P)
        are treated as literal text — raw bytes in the widget. Even bypassing
        from_ansi() doesn't help: Textual renders each row independently with
        explicit cursor moves between rows, and those cursor moves get embedded
        inside the DCS sequence, corrupting the image.
    Result: always use 'symbols' for TUI. We compensate with higher-quality
    chafa flags (font-ratio, color-extractor) for a sharper result.

    Config values respected:
      "auto"    (default) — symbols (best Textual-compatible mode)
      "symbols" — Unicode block/sextant art + full ANSI color
      "ascii"   — symbols mode restricted to ASCII range
      "sixel"   — ignored in TUI context; falls back to symbols
    """
    if config is not None:
        fmt = getattr(config, "thumbnail_format", None)
        if fmt is None:
            fmt = config.get("thumbnail_format", "auto") if hasattr(config, "get") else "auto"
    else:
        fmt = "auto"

    # ascii restricts the symbol set; everything else (incl. sixel/auto) → full symbols
    if fmt == "ascii":
        return "ascii"
    return "symbols"


def _has_chafa() -> bool:
    return _platform_has_chafa()


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
    # Ensure cache directory exists before writing
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.debug("Thumbnail cache dir create failed for %s: %s", video_id, exc)
        return None
    try:
        from src.platform import get_popen_kwargs
        cmd = get_thumbnail_download_cmd(url, str(dest))
        result = subprocess.run(
            cmd,
            capture_output=True,
            **get_popen_kwargs(headless=True),
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 100:
            logger.debug("Downloaded thumbnail for %s", video_id)
            return dest
        dest.unlink(missing_ok=True)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
            logger.debug(
                "Thumbnail download failed for %s (rc=%d)%s",
                video_id, result.returncode,
                f": {stderr}" if stderr else "",
            )
        return None
    except Exception as exc:
        logger.debug("Thumbnail download error for %s: %s", video_id, exc)
        dest.unlink(missing_ok=True)
        return None



# ── PIL half-block fallback ────────────────────────────────────────────────────

def render_pil_halfblock(
    video_id: str,
    entry: dict,
    *,
    cols: int = 38,
    rows: int = 20,
) -> str:
    """Render thumbnail as 24-bit colored Unicode half-block art using Pillow.

    Each terminal cell covers 2 pixel rows: the upper half-block character (▀)
    is drawn with the top pixel as foreground color and the bottom pixel as
    background color, giving effectively double the vertical resolution.

    Used on Windows when neither chafa nor a Sixel/TGP protocol is available
    (e.g. running inside the Cursor IDE terminal instead of Windows Terminal).
    Pillow is a hard dependency (requirements.txt) so this always works.

    Result is cached to CHAFA_DIR with a ``_pil`` format suffix so re-renders
    at the same size are free.
    """
    cache_path = _chafa_cache_path(video_id, cols, rows, "pil")
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
                # ESC[38;2;r;g;bm  = set foreground (upper pixel)
                # ESC[48;2;r;g;bm  = set background (lower pixel)
                # ▀ = upper half block
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
        _ensure_chafa_dir()
        try:
            cache_path.write_text(ansi, encoding="utf-8")
        except OSError:
            pass

    return ansi


# ── URL selection ──────────────────────────────────────────────────────────────

def _best_thumb_url(entry: dict) -> str:
    """Pick the best thumbnail URL from a yt-dlp entry."""
    # Use pre-normalised 'thumbnail' field first (set by ytdlp._normalise_entry)
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


# ── Render ─────────────────────────────────────────────────────────────────────

def render(
    video_id: str,
    entry: dict,
    *,
    cols: int = 38,
    rows: int = 20,
    config=None,
    on_proc_started: Callable[[subprocess.Popen], None] | None = None,
) -> str:
    """
    Return chafa ANSI output for the video's thumbnail, safe for Textual TUI rendering.

    Uses _chafa_format_for_tui() — never emits Kitty graphics protocol (binary),
    which would appear as garbage inside Rich.Text.from_ansi().

    Caching: re-rendering the same (video_id, cols, rows, fmt) hits the disk
    cache (~/.cache/termtube/chafa/) and skips the chafa subprocess entirely.

    config: optional Config object; if provided its thumbnail_format setting is used.
    on_proc_started: optional callback receiving the chafa Popen for cancellation
    by the caller. Not invoked on cache hits.
    Downloads thumbnail if not cached. Returns empty string if unavailable.
    """
    if not _has_chafa():
        return ""

    fmt = _chafa_format_for_tui(config)
    cache_key_fmt = "ascii" if fmt == "ascii" else "symbols"

    # ── Disk cache lookup ─────────────────────────────────────────────────────
    cache_path = _chafa_cache_path(video_id, cols, rows, cache_key_fmt)
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding="utf-8")
        except OSError:
            pass

    local = _thumb_path(video_id)
    if not local.exists():
        url = _best_thumb_url(entry)
        if not url:
            logger.debug("No thumbnail URL for %s", video_id)
            return ""
        local = download(video_id, url) or Path("")

    if not local.exists():
        return ""

    # Build chafa flags.
    # --font-ratio=0.5  accounts for typical terminal font aspect (2:1 h:w),
    #                   giving correct aspect ratio for the thumbnail.
    # --color-extractor=average  better colour sampling than default.
    # --optimize=1       light dithering — visually nearly identical to =3 at
    #                    a fraction of the CPU cost (=3 was a major spike source).
    # NOTE: --color-space=din99d removed — perceptual matrix conversion per
    # pixel was expensive and made no visible difference for thumbnails.
    base_quality = [
        "--font-ratio=0.5",
        "--color-extractor=average",
        "--optimize=1",
    ]
    if fmt == "ascii":
        extra_flags = ["--symbols=ascii", *base_quality]
        out_fmt = "symbols"
    else:
        extra_flags = base_quality
        out_fmt = fmt

    try:
        from src.platform import get_popen_kwargs
        chafa_exe = get_chafa_exe() or "chafa"
        proc = subprocess.Popen(
            [
                chafa_exe,
                f"--size={cols}x{rows}",
                f"--format={out_fmt}",
                *extra_flags,
                str(local),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            **get_popen_kwargs(headless=True),
        )
    except (FileNotFoundError, OSError) as exc:
        logger.debug("chafa spawn error for %s: %s", video_id, exc)
        return ""

    if on_proc_started is not None:
        try:
            on_proc_started(proc)
        except Exception:
            pass

    try:
        stdout, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
        logger.debug("chafa render timeout for %s", video_id)
        return ""
    except Exception as exc:
        logger.debug("chafa render error for %s: %s", video_id, exc)
        return ""

    # If the process was killed mid-render (e.g. cursor moved on) the returncode
    # is non-zero and stdout may be empty/partial — don't cache that.
    if proc.returncode not in (0, None):
        return stdout or ""

    # Persist to disk cache for next time.
    if stdout:
        _ensure_chafa_dir()
        try:
            cache_path.write_text(stdout, encoding="utf-8")
        except OSError:
            pass
    return stdout or ""


def prune_old_chafa(max_age_days: int = 7, max_count: int = 600) -> None:
    """Delete cached chafa ANSI files older than max_age_days, then cap to max_count."""
    if not CHAFA_DIR.exists():
        return
    import time as _time
    cutoff = _time.time() - max_age_days * 86400
    files: list[tuple[float, Path]] = []
    deleted = 0
    for f in CHAFA_DIR.glob("*.ansi"):
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
    logger.debug("prune_old_chafa: %d expired, %d capped, %d kept",
                 deleted, capped, max(0, len(files) - capped))
