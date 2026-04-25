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

        self.sub_title = self._image_mode_label()

        from src.tui.screens.main_screen import MainScreen
        self.push_screen(MainScreen())

    @staticmethod
    def _image_mode_label() -> str:
        """Subtitle showing the active image rendering mode."""
        try:
            from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE
            if not _HAS_TEXTUAL_IMAGE:
                return "symbols mode"
            from textual_image.renderable import Image as _Auto
            from textual_image.renderable.tgp      import Image as _TGP
            from textual_image.renderable.sixel    import Image as _Sixel
            from textual_image.renderable.halfcell import Image as _Half
            name = {_TGP: "TGP", _Sixel: "sixel", _Half: "halfcell"}.get(_Auto, "")
            return f"images · {name}" if name else "symbols mode"
        except Exception:
            return ""
