"""TermTube v2 — Textual App root."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer

import cache as _cache
import logger
from config import Config

THEME_CLASSES = {
    "crimson":  "",
    "amber":    "theme-amber",
    "ocean":    "theme-ocean",
    "midnight": "theme-midnight",
    "forest":   "theme-forest",
}


class TermTubeApp(App):
    TITLE = "TermTube"
    CSS_PATH = "theme.tcss"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._theme_class = ""

    def on_mount(self) -> None:
        # Apply theme
        theme = self.config.get("theme", "crimson")
        cls = THEME_CLASSES.get(theme, "")
        if cls:
            self.add_class(cls)
        self._theme_class = cls

        # Housekeeping: deferred 60s after mount to not compete with startup
        self.set_timer(60, self._run_housekeeping)

        # Push main screen
        from tui.screens.main_screen import MainScreen
        self.push_screen(MainScreen(self.config))

    def on_unmount(self) -> None:
        self._run_housekeeping()

    def _run_housekeeping(self) -> None:
        try:
            _cache.prune_old_thumbnails()
            _cache.prune_old_videos()
            _cache.prune_old_sb()
        except Exception as exc:
            logger.debug("housekeeping error: %s", exc)

    def apply_theme(self, theme: str) -> None:
        """Switch theme at runtime (called from settings modal)."""
        if self._theme_class:
            self.remove_class(self._theme_class)
        cls = THEME_CLASSES.get(theme, "")
        if cls:
            self.add_class(cls)
        self._theme_class = cls
        self.config.set("theme", theme)
