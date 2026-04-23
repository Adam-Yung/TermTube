"""MyYouTubeApp — Textual application entry point."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from src.cache import Cache
from src.config import Config


class MyYouTubeApp(App):
    """
    MyYouTube — YouTube TUI powered by yt-dlp + Textual.

    config and cache are stored on the App so any widget can access them via
    self.app.config / self.app.cache without passing them through constructors.
    """

    TITLE = "MyYouTube"
    SUB_TITLE = "YouTube in your terminal"
    CSS_PATH = Path(__file__).parent / "theme.tcss"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.cache = Cache(config._data.get("cache_ttl", {}))

    def on_mount(self) -> None:
        from src.tui.screens.main_screen import MainScreen
        self.push_screen(MainScreen())
