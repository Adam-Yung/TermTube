"""TermTubeApp — Textual application entry point."""

from __future__ import annotations

import atexit
import threading
from pathlib import Path

from textual.app import App, ComposeResult
from textual.message import Message

from src import logger
from src.cache import Cache
from src.config import Config

_VALID_THEMES = {"crimson", "amber", "ocean", "midnight"}

# Housekeeping fires once 60 s after mount so the home feed renders without
# competing for disk I/O. It also runs on unmount as a backstop.
_HOUSEKEEPING_DELAY_S = 60.0


class TermTubeApp(App):
    """
    TermTube — YouTube TUI powered by yt-dlp + Textual.

    config and cache are stored on the App so any widget can access them via
    self.app.config / self.app.cache.
    """

    class PlayerStateUpdated(Message):
        """Broadcast from the App after each audio IPC poll.

        Other screens (e.g. ChannelScreen) subscribe to this message to sync
        their ActionBar without needing their own independent IPC poll timer.
        """
        def __init__(self, pos: float, dur: float, paused: bool, playing: bool) -> None:
            super().__init__()
            self.pos = pos
            self.dur = dur
            self.paused = paused
            self.playing = playing

    TITLE = "TermTube"
    CSS_PATH = Path(__file__).parent / "theme.tcss"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.cache = Cache(config._data.get("cache_ttl", {}))
        self._housekeeping_done = threading.Event()
        atexit.register(self._atexit_cleanup)

    def on_mount(self) -> None:
        # Clean up any orphaned processes/sockets from a previous crash
        from src.platform import reap_orphans
        try:
            reap_orphans()
        except Exception:
            pass

        # Apply colour theme as a CSS class on the App root
        theme = self.config.theme
        logger.debug("App mounting (theme=%s)", theme)
        if theme in _VALID_THEMES and theme != "crimson":
            self.add_class(f"theme-{theme}")

        # Defer housekeeping until 60 s after launch so it doesn't compete with
        # the home feed render. If the app is closed earlier, on_unmount runs
        # the same prune as a backstop.
        self.set_timer(_HOUSEKEEPING_DELAY_S, self._launch_housekeeping)

        from src.tui.screens.main_screen import MainScreen

        self.push_screen(MainScreen())

    def on_unmount(self) -> None:
        # Kill all tracked subprocesses so they don't orphan on exit.
        try:
            from src.platform import ProcessRegistry
            ProcessRegistry.get().kill_all(timeout=1.5)
        except Exception:
            pass
        try:
            import src.ytdlp as ytdlp
            ytdlp.cancel_all()
        except Exception:
            pass
        # Backstop: if the user quits before the 60 s timer fires, still prune
        # before exit. Synchronous run is fine — process is exiting anyway.
        if not self._housekeeping_done.is_set():
            self._run_housekeeping()

    def _launch_housekeeping(self) -> None:
        if self._housekeeping_done.is_set():
            return
        threading.Thread(target=self._run_housekeeping, daemon=True).start()

    def _run_housekeeping(self) -> None:
        """Prune stale files from the cache directories."""
        if self._housekeeping_done.is_set():
            return
        self._housekeeping_done.set()
        try:
            logger.debug("Housekeeping: pruning thumbnails + video JSON + rendered cache")
            # Pin playlist videos before pruning to protect them
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
            # Fail silently so it never crashes the TUI

    @staticmethod
    def _atexit_cleanup() -> None:
        """Last-resort cleanup: kill any orphaned subprocesses on exit."""
        try:
            from src.platform import ProcessRegistry
            ProcessRegistry.get().kill_all(timeout=1.5)
        except Exception:
            pass
        try:
            import src.ytdlp as ytdlp
            ytdlp.cancel_all()
        except Exception:
            pass
