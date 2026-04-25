"""TermTubeApp — Textual application entry point."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from src.cache import Cache
from src.config import Config

_VALID_THEMES = {"crimson", "amber", "ocean", "midnight"}


class TermTubeApp(App):
    """
    TermTube — YouTube TUI powered by yt-dlp + Textual.

    config and cache are stored on the App so any widget can access them via
    self.app.config / self.app.cache.
    """

    TITLE = "TermTube"
    CSS_PATH = Path(__file__).parent / "theme.tcss"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.cache = Cache(config._data.get("cache_ttl", {}))

    def on_mount(self) -> None:
        # Apply colour theme as a CSS class on the App root
        theme = self.config.theme
        if theme in _VALID_THEMES and theme != "crimson":
            self.add_class(f"theme-{theme}")

        from src.tui.screens.main_screen import MainScreen
        self.push_screen(MainScreen())
