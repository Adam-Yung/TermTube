"""TermTubeApp: Textual app root. Owns config, cache and process cleanup."""

from __future__ import annotations

import atexit
import sys
import threading
from pathlib import Path

from textual.app import App

from src import logger, store
from src.cache import Cache
from src.config import Config
from src.tui.audio_controller import AudioController
from src.tui.fmt import escape_markup
from src.tui.layout import HORIZONTAL_BREAKPOINTS

_HOUSEKEEPING_DELAY_S = 60.0


class TermTubeApp(App):
    """`config` and `cache` live here so widgets reach them as `self.app.config` / `self.app.cache`."""

    TITLE = "TermTube"
    CSS_PATH = Path(__file__).parent / "theme.tcss"
    ENABLE_COMMAND_PALETTE = False
    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.cache = Cache(config.get("cache_ttl", {}))
        self._housekeeping_done = threading.Event()
        self.audio = AudioController(self)
        atexit.register(self._atexit_cleanup)

    def notify(self, message, *, title="", severity="information", timeout=None, markup=True) -> None:
        """Textual's ``notify`` with text escaped: our notices are plain, and titles contain ``[brackets]``."""
        super().notify(
            escape_markup(message) if markup else message,
            title=title, severity=severity, timeout=timeout, markup=markup,
        )

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

        store.set_failure_hook(self._store_save_failed)
        threading.Thread(target=self._warmup_ytdlp, daemon=True).start()
        self.set_timer(_HOUSEKEEPING_DELAY_S, self._launch_housekeeping)

        from src.tui.screens.main_screen import MainScreen

        self.push_screen(MainScreen())

    def _store_save_failed(self, message: str) -> None:
        """Tell the user from whichever thread the failing save ran on."""
        if threading.get_ident() == self._thread_id:
            self.notify(message, severity="error", timeout=8)
        else:
            self.call_from_thread(self.notify, message, severity="error", timeout=8)

    def call_ui(self, fn, *args, **kwargs):
        """``call_from_thread`` for a worker thread that may outlive the app: once it is closing the call is dropped.

        A closed loop would raise ``RuntimeError`` in the thread and leave the callback coroutine unawaited.
        """
        if not self.is_running:
            return None
        try:
            return self.call_from_thread(fn, *args, **kwargs)
        except RuntimeError:
            if self.is_running:
                raise
            return None

    def on_unmount(self) -> None:
        store.set_failure_hook(None)
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
            self.cache.prune_old_searches()
            from src import sponsorblock

            sponsorblock.prune_cache()
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
