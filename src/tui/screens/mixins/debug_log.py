from __future__ import annotations

import queue
import re

from textual.widgets import RichLog

from src import logger
from src.strings import text

_LEVEL_STYLES = {
    "DEBUG": "dim",
    "INFO": "cyan",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red bold",
}
_DRAIN_INTERVAL_S = 0.2
_DRAIN_MAX_PER_TICK = 200
_MARKUP = re.compile(r"\[/?[^\]]*\]")


class DebugLogMixin:
    """Ctrl+D log panel fed by the ``--debug`` logger.

    The screen composes a ``RichLog`` with id ``debug-log`` and calls ``_init_debug_log``
    from ``__init__`` and ``_mount_debug_log`` from ``on_mount``.
    """

    def _init_debug_log(self) -> None:
        self._log_visible = False
        self._log_queue: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()

    def _mount_debug_log(self) -> None:
        self.query_one("#debug-log").display = False
        if logger.is_debug():
            logger.register_tui_sink(self._on_log_record)
            self.set_interval(_DRAIN_INTERVAL_S, self._drain_log_queue)
            logger.info("debug log wired to TUI sink")
            self._log(text("debug_log.active", file=logger.log_file()))

    def action_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        log = self.query_one("#debug-log", RichLog)
        log.display = self._log_visible
        if not self._log_visible:
            return
        if not logger.is_debug():
            log.clear()
            log.write(text("debug_log.disabled"))
            log.write(text("debug_log.restart_hint"))
            log.write(text("debug_log.log_location"))
        self.notify(text("debug_log.visible"), timeout=2)

    def _on_log_record(self, level: str, msg: str) -> None:
        """Logger sink, called from any thread while the logging handler lock is held: it must never block.

        ``call_from_thread`` blocks until the UI thread runs the callback; if the UI thread is itself waiting for
        that handler lock (it logs too), both wait forever. The queue is drained on a UI timer instead.
        """
        self._log_queue.put((level, msg))

    def _drain_log_queue(self) -> None:
        for _ in range(_DRAIN_MAX_PER_TICK):
            try:
                level, msg = self._log_queue.get_nowait()
            except queue.Empty:
                return
            self._write_log_record(level, msg)

    def _write_log_record(self, level: str, msg: str) -> None:
        color = _LEVEL_STYLES.get(level, "white")
        safe = msg.replace("[", "\\[") if msg else ""
        try:
            self.query_one("#debug-log", RichLog).write(
                f"[{color}]\\[{level[0]}][/{color}] {safe}"
            )
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        """Write a Rich-markup line to the panel and its plain text to the log file."""
        if not logger.is_debug():
            return
        try:
            self.query_one("#debug-log", RichLog).write(msg)
        except Exception:
            pass
        logger.file_only(_MARKUP.sub("", msg))
