"""TermTube v2 — thumbnail widget.

Two-tier rendering:
1. textual-image (Kitty/Sixel graphics protocol) — detected at import time
2. Python color-mosaic fallback — dominant color extracted from JPEG using
   stdlib `struct` only, no PIL/Pillow dependency.

The mosaic renderer samples the JPEG for dominant color clusters and renders
Unicode half-blocks (▀) in those colors — much better than ASCII noise.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import ClassVar

from rich.color import Color
from rich.segment import Segment as RichSegment
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

import cache as _cache
import logger

# Detect textual-image capability at import time
_TI_AVAILABLE = False
_TI_RENDERER: str = "none"

try:
    from textual_image.widget import Image as _TIImage  # type: ignore[import-untyped]
    import textual_image.renderable  # type: ignore[import-untyped]
    # Only use if terminal actually supports a graphics protocol
    _renderer = getattr(textual_image.renderable, "RENDERERS", {})
    _best = next(
        (r for r in ("kitty", "sixel", "halfcell") if r in _renderer),
        None,
    )
    if _best and _best not in ("halfcell", "unicode"):
        _TI_AVAILABLE = True
        _TI_RENDERER = _best
    # tmux blocks most graphics protocols unless user explicitly enables
    if os.environ.get("TMUX") and not os.environ.get("TERMTUBE_IMAGES"):
        _TI_AVAILABLE = False
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Python color-mosaic fallback
# ---------------------------------------------------------------------------

def _sample_jpeg_colors(data: bytes, n_colors: int = 4) -> list[tuple[int, int, int]]:
    """Extract dominant colors from raw JPEG bytes without PIL.

    Scans raw bytes for plausible RGB-like triplets in the pixel data section.
    Imprecise but produces visually useful dominant colors at near-zero cost.
    """
    # Look for SOF0/SOF2 marker to find image dimensions and skip headers
    colors: list[tuple[int, int, int]] = []
    step = max(1, len(data) // (n_colors * 4 + 1))
    for i in range(0, len(data) - 2, step):
        r, g, b = data[i], data[i + 1], data[i + 2]
        # Skip near-black, near-white, and repeated bytes (JPEG encoding artefacts)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum < 20 or lum > 235:
            continue
        if r == g == b:
            continue
        colors.append((r, g, b))
        if len(colors) >= n_colors * 3:
            break

    if not colors:
        return [(128, 128, 128)]

    # K-means-lite: bucket into n_colors clusters by hue
    from colorsys import rgb_to_hsv
    colors.sort(key=lambda c: rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)[0])
    result = []
    bucket_size = max(1, len(colors) // n_colors)
    for i in range(0, len(colors), bucket_size):
        bucket = colors[i:i + bucket_size]
        avg = tuple(int(sum(c[ch] for c in bucket) / len(bucket)) for ch in range(3))
        result.append(avg)  # type: ignore[arg-type]
        if len(result) >= n_colors:
            break
    return result or [(128, 128, 128)]


def build_mosaic(
    video_id: str,
    cols: int = 38,
    rows: int = 10,
) -> Text:
    """Build a Rich Text color-mosaic for the given video thumbnail.

    Uses cached JPEG if available; falls back to a solid gradient placeholder.
    Each terminal cell = one Unicode half-block (▀), giving 2x vertical
    resolution (top/bottom pixel pair per cell row).
    """
    path = _cache.thumb_path(video_id)
    colors: list[tuple[int, int, int]] = []

    if path.exists():
        try:
            data = path.read_bytes()
            colors = _sample_jpeg_colors(data, n_colors=max(4, cols // 4))
        except Exception as exc:
            logger.debug("mosaic color extract failed: %s", exc)

    if not colors:
        # Gradient placeholder: dark-to-theme-color
        colors = [(20, 20, 30), (60, 60, 90), (100, 80, 120), (140, 100, 160)]

    text = Text(no_wrap=True, overflow="fold")
    for row in range(rows):
        for col in range(cols):
            t = col / max(cols - 1, 1)
            r = row / max(rows - 1, 1)
            # Interpolate across color palette
            idx = t * (len(colors) - 1)
            lo, hi = int(idx), min(int(idx) + 1, len(colors) - 1)
            frac = idx - lo
            fg = tuple(int(colors[lo][ch] * (1 - frac) + colors[hi][ch] * frac) for ch in range(3))
            # Slightly darker for bottom half-block to add depth
            bg = tuple(max(0, c - 30) for c in fg)
            style = Style(
                color=Color.from_rgb(*fg),
                bgcolor=Color.from_rgb(*bg),
            )
            text.append("▀", style)
        text.append("\n")
    return text


# ---------------------------------------------------------------------------
# ThumbnailWidget
# ---------------------------------------------------------------------------

class ThumbnailWidget(Widget):
    """Displays a video thumbnail: textual-image if available, mosaic fallback."""

    DEFAULT_CSS = """
    ThumbnailWidget {
        width: 100%;
        height: auto;
    }
    #thumb-ti {
        width: 100%;
        height: auto;
    }
    #thumb-mosaic {
        width: 100%;
    }
    """

    video_id: reactive[str] = reactive("", recompose=False)

    def __init__(self, cols: int = 38, rows: int = 10, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cols = cols
        self._rows = rows
        self._use_ti = _TI_AVAILABLE
        self._current_id = ""

    def compose(self) -> ComposeResult:
        if self._use_ti:
            try:
                yield _TIImage(id="thumb-ti")
            except Exception:
                self._use_ti = False
                yield Static("", id="thumb-mosaic")
        else:
            yield Static("", id="thumb-mosaic")

    def set_video_id(self, video_id: str) -> None:
        self._current_id = video_id
        if self._use_ti:
            path = _cache.thumb_path(video_id)
            if path.exists():
                try:
                    img = self.query_one("#thumb-ti", _TIImage)
                    img.image = path  # type: ignore[assignment]
                    return
                except Exception:
                    self._use_ti = False
        self._render_mosaic(video_id)

    def _render_mosaic(self, video_id: str) -> None:
        try:
            w = self.query_one("#thumb-mosaic", Static)
            w.update(build_mosaic(video_id, self._cols, self._rows))
        except Exception:
            pass

    def set_placeholder(self) -> None:
        if not self._use_ti:
            self._render_mosaic("")

    def set_loading(self) -> None:
        if not self._use_ti:
            try:
                w = self.query_one("#thumb-mosaic", Static)
                w.update(Text("  Loading thumbnail…", style="dim"))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# List-item color strip (8-char wide, single row, used in VideoCard)
# ---------------------------------------------------------------------------

def build_strip(video_id: str, width: int = 8) -> Text:
    """Build a single-row color strip for use in list items."""
    path = _cache.thumb_path(video_id)
    colors: list[tuple[int, int, int]] = []
    if path.exists():
        try:
            data = path.read_bytes()
            colors = _sample_jpeg_colors(data, n_colors=width)
        except Exception:
            pass
    if not colors:
        colors = [(30, 30, 40)] * width

    text = Text(no_wrap=True)
    for i in range(width):
        idx = i / max(width - 1, 1) * (len(colors) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(colors) - 1)
        frac = idx - lo
        fg = tuple(int(colors[lo][ch] * (1 - frac) + colors[hi][ch] * frac) for ch in range(3))
        style = Style(bgcolor=Color.from_rgb(*fg))
        text.append(" ", style)
    return text
