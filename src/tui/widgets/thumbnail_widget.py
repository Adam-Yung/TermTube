"""ThumbnailWidget — high-quality thumbnail display via textual-image (TGP/sixel/halfcell).

Falls back to chafa ANSI symbol art when textual-image is not available.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

# ── Optional textual-image integration ────────────────────────────────────────
# textual_image.widget MUST be imported before Textual starts (terminal detection
# and cell-size query run at import time and won't work after Textual's I/O threads
# are running). main.py does this import at the right moment.

_HAS_TEXTUAL_IMAGE = False
try:
    from textual_image.widget import Image as _TIImage  # type: ignore[import]
    _HAS_TEXTUAL_IMAGE = True
except ImportError:
    pass


class ThumbnailWidget(Widget):
    """
    Thumbnail display widget.

    When textual-image is installed it renders via TGP (Kitty) or sixel (other
    terminals) — real pixel-quality images. Otherwise falls back to chafa ANSI
    symbol art passed in via set_ansi().
    """

    DEFAULT_CSS = """
    ThumbnailWidget {
        background: #050505;
        width: 100%;
        height: 100%;
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
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_id: str = ""

    def compose(self) -> ComposeResult:
        yield Static("[dim]▪ No thumbnail[/dim]", id="thumb-status", markup=True)
        if _HAS_TEXTUAL_IMAGE:
            yield _TIImage(id="thumb-image")  # type: ignore[call-arg]

    def on_mount(self) -> None:
        # Hide the image widget until we have an image to show
        if _HAS_TEXTUAL_IMAGE:
            try:
                self.query_one("#thumb-image").display = False
            except Exception:
                pass

    # ── Public API ────────────────────────────────────────────────────────────

    def set_video_id(self, video_id: str) -> None:
        """Set the active video ID to guard against stale updates."""
        self._current_id = video_id

    def set_loading(self) -> None:
        """Show a loading placeholder."""
        self._show_status("[dim]⏳ Loading…[/dim]")

    def set_placeholder(self) -> None:
        """Show a 'no thumbnail' placeholder."""
        self._show_status("[dim]▪ No thumbnail[/dim]")

    def set_image_path(self, video_id: str, path: Path) -> None:
        """Display a thumbnail from a filesystem path via textual-image.

        Called from main thread (via call_from_thread). Only acts if video_id
        matches the currently selected video and textual-image is available.
        """
        if video_id != self._current_id:
            return
        if not _HAS_TEXTUAL_IMAGE:
            return
        try:
            img = self.query_one("#thumb-image")
            img.image = path  # type: ignore[attr-defined]
            img.display = True
            self.query_one("#thumb-status").display = False
        except Exception:
            self.set_placeholder()

    def set_ansi(self, video_id: str, ansi: str) -> None:
        """Fallback: display chafa ANSI art inside the status Static.

        Used when textual-image is not installed. When textual-image IS present
        this is a no-op (set_image_path handles display instead).
        """
        if video_id != self._current_id:
            return
        if _HAS_TEXTUAL_IMAGE:
            return  # textual-image handles rendering
        if ansi:
            try:
                from rich.text import Text
                self.query_one("#thumb-status", Static).update(Text.from_ansi(ansi))
                self.query_one("#thumb-status").display = True
            except Exception:
                self.set_placeholder()
        else:
            self.set_placeholder()

    # ── Helpers ───────────────────────────────────────────────────────────────

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
