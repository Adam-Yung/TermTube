"""TermTube v2 — logging module.

Identical in spirit to v1. Two modes:
- Without --debug: level set above CRITICAL, no handlers → every logger.*
  call is a zero-cost no-op (single integer comparison in CPython).
- With --debug: writes to $TMPDIR/TermTube/<timestamp>.log and forwards to
  a registered TUI sink via call_from_thread.

Nothing is ever written to stderr — Textual owns the terminal.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

_logger = logging.getLogger("termtube")
_log_file: Path | None = None
_tui_sink: Callable[[logging.LogRecord], None] | None = None
_sink_lock = threading.Lock()
_debug_enabled = False


class _FileHandler(logging.FileHandler):
    """File handler that optionally forwards to the TUI sink."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        with _sink_lock:
            sink = _tui_sink
        if sink is not None and not getattr(record, "_termtube_skip_tui", False):
            try:
                sink(record)
            except Exception:
                pass


def setup(*, debug: bool = False, level: str = "ALL") -> None:
    """Initialise logging.  Call once from main.py before launching the app."""
    global _log_file, _debug_enabled
    _debug_enabled = debug

    if not debug:
        _logger.setLevel(logging.CRITICAL + 1)
        _logger.handlers.clear()
        return

    log_level = logging.DEBUG if level in ("ALL", "DEBUG") else getattr(logging, level, logging.DEBUG)
    _logger.setLevel(log_level)
    _logger.handlers.clear()

    tmp = Path(tempfile.gettempdir()) / "TermTube"
    tmp.mkdir(parents=True, exist_ok=True)
    _log_file = tmp / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    handler = _FileHandler(_log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s"))
    _logger.addHandler(handler)
    _logger.propagate = False


def is_debug() -> bool:
    return _debug_enabled


def log_file() -> Path | None:
    return _log_file


def register_tui_sink(cb: Callable[[logging.LogRecord], None]) -> None:
    global _tui_sink
    with _sink_lock:
        _tui_sink = cb


def unregister_tui_sink() -> None:
    global _tui_sink
    with _sink_lock:
        _tui_sink = None


def file_only(msg: str, *args: object) -> None:
    """Log to file only — skip TUI sink.  Used for structured TUI log writes."""
    if not _debug_enabled:
        return
    record = _logger.makeRecord(
        _logger.name, logging.DEBUG, "(file_only)", 0, msg, args, None
    )
    record._termtube_skip_tui = True  # type: ignore[attr-defined]
    _logger.handle(record)


# Convenience aliases
debug = _logger.debug
info = _logger.info
warning = _logger.warning
error = _logger.error
critical = _logger.critical
