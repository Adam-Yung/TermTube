"""ThumbnailWidget — renders chafa ANSI art inside a Textual Static widget."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static


class ThumbnailWidget(Static):
    """Displays a chafa-rendered thumbnail as ANSI art."""

    DEFAULT_CSS = """
    ThumbnailWidget {
        background: #050505;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._current_id: str = ""

    def set_loading(self) -> None:
        self.update("[dim]⏳ Loading thumbnail…[/dim]")

    def set_placeholder(self) -> None:
        self.update("[dim]▪ No thumbnail[/dim]")

    def set_ansi(self, video_id: str, ansi: str) -> None:
        """Set thumbnail content. Ignores stale updates for a different video."""
        if video_id != self._current_id:
            return
        if ansi:
            self.update(Text.from_ansi(ansi))
        else:
            self.set_placeholder()

    def set_video_id(self, video_id: str) -> None:
        """Set the active video ID to guard against stale thumbnail updates."""
        self._current_id = video_id
