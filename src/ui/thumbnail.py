"""Thumbnail rendering via chafa — download URL → render to ANSI terminal art.

Supports both symbols mode (universal) and kitty graphics protocol
(high-quality images, auto-detected from KITTY_WINDOW_ID environment variable).
"""

from __future__ import annotations
import os
import shutil
import subprocess
import threading
from pathlib import Path

from src.cache import THUMB_DIR
from src import logger


# ── Terminal detection ─────────────────────────────────────────────────────────

def _is_kitty() -> bool:
    """True if running inside kitty (even through tmux)."""
    return bool(os.environ.get("KITTY_WINDOW_ID"))


def _supports_sixel() -> bool:
    """Heuristic: return True when the terminal is known to support sixel graphics.

    NOTE: This is specifically for *sixel* (DCS escape sequences), NOT for the
    Kitty native graphics protocol (which is binary and cannot go through Rich).
    Kitty 0.20+ supports sixel as a compatibility layer, so kitty is included.

    Checked env vars (fastest, no I/O needed):
      KITTY_WINDOW_ID — Kitty ≥ 0.20 supports sixel
      TERM_PROGRAM    — "iTerm.app" (iTerm2) and "WezTerm"
      TERM            — "foot", "mlterm"
      XTERM_VERSION   — xterm compiled with sixel support
    """
    if _is_kitty():
        return True  # Kitty ≥ 0.20 supports sixel (separate from its native protocol)
    term_prog = os.environ.get("TERM_PROGRAM", "")
    if term_prog in ("iTerm.app", "WezTerm"):
        return True
    term = os.environ.get("TERM", "")
    if term in ("foot", "mlterm"):
        return True
    if os.environ.get("MLTERM"):
        return True
    # xterm with sixel support announces itself via XTERM_VERSION
    if os.environ.get("XTERM_VERSION") and "xterm" in term:
        return True
    return False


def _chafa_format() -> str:
    """Return the best chafa output format for the current terminal (CLI/fzf context)."""
    if _is_kitty() and shutil.which("chafa"):
        return "kitty"
    if _supports_sixel():
        return "sixel"
    return "symbols"


def _chafa_format_for_tui(config=None) -> str:
    """Return the chafa format for the Textual TUI, respecting config + terminal caps.

    Never returns 'kitty' — Kitty graphics protocol is binary and cannot be
    parsed by Rich.Text.from_ansi().

    Config thumbnail_format values:
      "auto"    (default) — sixel when the terminal supports it, else symbols
      "sixel"   — always try sixel (user opt-in)
      "symbols" — Unicode block art + ANSI colors (works everywhere)
      "ascii"   — symbols mode restricted to ASCII chars (most compatible)
    """
    if config is not None:
        fmt = getattr(config, "thumbnail_format", None)
        if fmt is None:
            fmt = config.get("thumbnail_format", "auto") if hasattr(config, "get") else "auto"
    else:
        fmt = "auto"

    if fmt == "sixel":
        return "sixel"
    if fmt in ("symbols", "ascii"):
        return fmt
    # "auto" — detect at runtime
    if _supports_sixel():
        return "sixel"
    return "symbols"


def _has_chafa() -> bool:
    return shutil.which("chafa") is not None


def _thumb_path(video_id: str) -> Path:
    return THUMB_DIR / f"{video_id}.jpg"


# ── Download ───────────────────────────────────────────────────────────────────

def download(video_id: str, url: str) -> Path | None:
    """Download thumbnail to cache using curl. Returns local path or None on failure."""
    if not url:
        return None
    dest = _thumb_path(video_id)
    if dest.exists():
        return dest
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "8", "-o", str(dest), url],
            capture_output=True,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 100:
            logger.debug("Downloaded thumbnail for %s", video_id)
            return dest
        dest.unlink(missing_ok=True)
        logger.debug("Thumbnail download failed for %s (curl rc=%d)", video_id, result.returncode)
        return None
    except Exception as exc:
        logger.debug("Thumbnail download error for %s: %s", video_id, exc)
        dest.unlink(missing_ok=True)
        return None


def download_background(video_ids_and_urls: list[tuple[str, str]], *, max_workers: int = 4) -> None:
    """
    Pre-download thumbnails for a list of (video_id, url) pairs in background threads.
    Skips IDs that are already cached. Fire-and-forget.
    """
    to_fetch = [(vid, url) for vid, url in video_ids_and_urls
                if vid and url and not _thumb_path(vid).exists()]
    if not to_fetch:
        return

    logger.debug("pre-downloading %d thumbnails in background", len(to_fetch))

    def _worker():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for vid, url in to_fetch:
                pool.submit(download, vid, url)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


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

def render(video_id: str, entry: dict, *, cols: int = 38, rows: int = 20, config=None) -> str:
    """
    Return chafa ANSI output for the video's thumbnail, safe for Textual TUI rendering.

    Uses _chafa_format_for_tui() — never emits Kitty graphics protocol (binary),
    which would appear as garbage inside Rich.Text.from_ansi().

    config: optional Config object; if provided its thumbnail_format setting is used.
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

    fmt = _chafa_format_for_tui(config)

    # Build chafa flags based on format
    extra_flags: list[str] = []
    if fmt == "ascii":
        # Restrict to plain ASCII-range symbols for maximum terminal compat
        extra_flags = ["--symbols=ascii", "--optimize=3"]
        fmt = "symbols"
    elif fmt == "sixel":
        pass  # No extra flags; sixel is self-contained
    else:
        extra_flags = ["--optimize=3"]

    try:
        result = subprocess.run(
            [
                "chafa",
                f"--size={cols}x{rows}",
                f"--format={fmt}",
                # No --stretch: preserve the 16:9 aspect ratio.
                # chafa will letterbox within the given size.
                *extra_flags,
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
    """Render a thumbnail from a URL directly (no caching). Pipes curl into chafa."""
    if not _has_chafa() or not url:
        return ""
    fmt = _chafa_format()
    extra_flags = [] if fmt == "kitty" else ["--optimize=3"]
    try:
        curl = subprocess.Popen(
            ["curl", "-sL", "--max-time", "8", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [
                "chafa",
                f"--size={cols}x{rows}",
                f"--format={fmt}",
                *extra_flags,
                "-",
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
