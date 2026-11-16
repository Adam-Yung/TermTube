from __future__ import annotations

import queue
import re

from textual.widgets import RichLog

from src import logger

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
            self._log(f"[green]Debug logging active[/green] — file: [dim]{logger.log_file()}[/dim]")

    def action_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        log = self.query_one("#debug-log", RichLog)
        log.display = self._log_visible
        if not self._log_visible:
            return
        if not logger.is_debug():
            log.clear()
            log.write("[yellow]Debug logging is disabled.[/yellow]")
            log.write("[dim]Restart with [bold]termtube --debug[/bold] to enable it.[/dim]")
            log.write("[dim]Logs go to $TMPDIR/TermTube/<timestamp>.log and are mirrored here.[/dim]")
        self.notify("Debug log visible — Ctrl+D to hide", timeout=2)

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
