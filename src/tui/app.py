"""TermTubeApp: Textual app root. Owns config, cache and process cleanup."""

from __future__ import annotations

import atexit
import sys
import threading
from pathlib import Path

from textual.app import App

from src import logger
from src.cache import Cache
from src.config import Config
from src.tui.audio_controller import AudioController

_HOUSEKEEPING_DELAY_S = 60.0


class TermTubeApp(App):
    """`config` and `cache` live here so widgets reach them as `self.app.config` / `self.app.cache`."""

    TITLE = "TermTube"
    CSS_PATH = Path(__file__).parent / "theme.tcss"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.cache = Cache(config._data.get("cache_ttl", {}))
        self._housekeeping_done = threading.Event()
        self.audio = AudioController(self)
        atexit.register(self._atexit_cleanup)

    def on_mount(self) -> None:
        from src.plat import reap_orphans
        try:
            reap_orphans()
        except Exception:
            pass

        theme = self.config.theme
        logger.debug("App mounting (theme=%s)", theme)
        if theme != "crimson":
            self.add_class(f"theme-{theme}")

        threading.Thread(target=self._warmup_ytdlp, daemon=True).start()
        self.set_timer(_HOUSEKEEPING_DELAY_S, self._launch_housekeeping)

        from src.tui.screens.main_screen import MainScreen

        self.push_screen(MainScreen())

    def on_unmount(self) -> None:
        self._atexit_cleanup()
        if not self._housekeeping_done.is_set():
            self._run_housekeeping()

    @staticmethod
    def _warmup_ytdlp() -> None:
        try:
            from src.ytdlp import warmup
            warmup()
        except Exception:
            pass

    def _launch_housekeeping(self) -> None:
        if self._housekeeping_done.is_set():
            return
        threading.Thread(target=self._run_housekeeping, daemon=True).start()

    def _run_housekeeping(self) -> None:
        if self._housekeeping_done.is_set():
            return
        self._housekeeping_done.set()
        try:
            logger.debug("Housekeeping: pruning thumbnails + video JSON + rendered cache")
            self.cache.pin_all_playlist_videos()
            self.cache.prune_old_thumbnails(max_age_days=7, max_count=300)
            self.cache.prune_old_videos(max_age_days=3, max_count=400)
            try:
                from src.ui.thumbnail import prune_old_rendered
                prune_old_rendered(max_age_days=7, max_count=600)
            except Exception:
                pass
        except Exception as exc:
            logger.exception("Housekeeping failed: %s", exc)

    @staticmethod
    def _atexit_cleanup() -> None:
        """Kill tracked subprocesses and cancel yt-dlp work. Idempotent; shared by `on_unmount` and `atexit`."""
        try:
            from src.plat import ProcessRegistry
            ProcessRegistry.get().kill_all(timeout=1.5)
        except Exception:
            pass
        try:
            ytdlp = sys.modules.get("src.ytdlp")
            if ytdlp:
                ytdlp.cancel_all()
        except Exception:
            pass
