"""Thumbnail display: textual-image (kitty/sixel) when usable, else PIL half-block ANSI."""

from __future__ import annotations

import os
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from src.plat import IS_WINDOWS

# textual_image probes the terminal at import time, so it must be imported before Textual
# starts its I/O threads (src/main.py does). Pixel images are off inside tmux (passthrough
# flickers) unless MYYOUTUBE_IMAGES=1.
_IN_TMUX = bool(os.environ.get("TMUX")) and not IS_WINDOWS
_FORCE_IMAGES = os.environ.get("MYYOUTUBE_IMAGES") == "1"

_HAS_TEXTUAL_IMAGE = False
if not _IN_TMUX or _FORCE_IMAGES:
    try:
        from textual_image.renderable import Image as _AutoRenderable
        from textual_image.renderable.unicode import Image as _UnicodeRenderable
        from textual_image.widget import Image as _TIImage
        if _AutoRenderable is not _UnicodeRenderable:
            _HAS_TEXTUAL_IMAGE = True
        elif IS_WINDOWS and bool(os.environ.get("WT_SESSION")):
            _HAS_TEXTUAL_IMAGE = True
    except ImportError:
        pass


class ThumbnailWidget(Widget):
    """Updates are keyed by id (`set_video_id`); a result for a stale id is dropped."""

    DEFAULT_CSS = """
    ThumbnailWidget {
        background: #050505;
        width: 100%;
        height: 100%;
        align: center middle;
    }

    #thumb-status {
        content-align: center middle;
        width: 100%;
        height: 100%;
        color: #444444;
    }

    #thumb-image {
        width: 100%;
        height: 100%;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_id: str = ""

    def compose(self) -> ComposeResult:
        yield Static("[dim]▪ No thumbnail[/dim]", id="thumb-status", markup=True)
        if _HAS_TEXTUAL_IMAGE:
            yield _TIImage(id="thumb-image")

    def on_mount(self) -> None:
        if _HAS_TEXTUAL_IMAGE:
            try:
                self.query_one("#thumb-image").display = False
            except Exception:
                pass

    def set_video_id(self, video_id: str) -> None:
        self._current_id = video_id

    def set_loading(self) -> None:
        self._show_status("[dim]⏳ Loading…[/dim]")

    def set_placeholder(self) -> None:
        self._show_status("[dim]▪ No thumbnail[/dim]")

    def set_image_path(self, video_id: str, path: Path) -> None:
        """Show an image file via textual-image; no-op without it."""
        if video_id != self._current_id:
            return
        if not _HAS_TEXTUAL_IMAGE:
            return
        try:
            img = self.query_one("#thumb-image")
            img.image = path
            img.display = True
            self.query_one("#thumb-status").display = False
        except Exception:
            self.set_placeholder()

    def set_ansi(self, video_id: str, ansi: str) -> None:
        """Show half-block ANSI art; no-op when textual-image is active."""
        if video_id != self._current_id:
            return
        if _HAS_TEXTUAL_IMAGE:
            return
        if ansi:
            try:
                self.query_one("#thumb-status", Static).update(Text.from_ansi(ansi))
                self.query_one("#thumb-status").display = True
            except Exception:
                self.set_placeholder()
        else:
            self.set_placeholder()

    def _show_status(self, text: str) -> None:
        try:
            self.query_one("#thumb-status", Static).update(text)
            self.query_one("#thumb-status").display = True
        except Exception:
            pass
        if _HAS_TEXTUAL_IMAGE:
            try:
                self.query_one("#thumb-image").display = False
            except Exception:
                pass
