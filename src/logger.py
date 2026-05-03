"""Logging for TermTube.

Behaviour:
  • Without --debug: the logger is set above CRITICAL — every logger.* call is a
    fast no-op (the level check happens before any formatting). No files are
    opened, no handlers attached, nothing is written.
  • With --debug: writes to a timestamped file in $TMPDIR/TermTube/ and (if a
    TUI sink is registered via register_tui_sink) mirrors to the in-app debug
    window. Nothing is written to stderr — that interferes with Textual's
    rendering.

Public API:
  setup(debug, level)     — call once at startup. level is one of
                            "ALL"|"DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL".
  is_debug()              — bool
  debug/info/warning/error/exception(msg, *args) — standard log calls
  file_only(msg, *args)   — write to file only, skip TUI sink. Used by UI code
                            that has already drawn a styled message into the
                            debug window itself.
  register_tui_sink(cb)   — cb(level: str, formatted_msg: str) is invoked from
                            inside the logger thread for each emitted record.
                            The callback is responsible for thread-safety
                            (e.g. App.call_from_thread).
  unregister_tui_sink()
"""

from __future__ import annotations
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

# Accepted level names for the --level CLI flag. "ALL" is an alias for DEBUG.
LEVEL_CHOICES = ("ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_LEVEL = "ALL"


def _resolve_level(name: str) -> int:
    upper = (name or "").upper()
    if upper in ("", "ALL"):
        return logging.DEBUG
    return getattr(logging, upper, logging.DEBUG)

_LOG_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "TermTube"
_log = logging.getLogger("termtube")
_log.propagate = False
_debug_enabled = False
_log_file: Path | None = None

# Sentinel attribute name set on records that should not be mirrored to the TUI
# (they were rendered there directly with markup by the screen itself).
_SKIP_TUI_ATTR = "_termtube_skip_tui"

_tui_sink: Callable[[str, str], None] | None = None


class _TUIHandler(logging.Handler):
    """Forwards records to the registered TUI sink, if any."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        if getattr(record, _SKIP_TUI_ATTR, False):
            return
        sink = _tui_sink
        if sink is None:
            return
        try:
            sink(record.levelname, self.format(record))
        except Exception:
            # The sink must never break logging.
            pass


def setup(debug: bool = False, level: str = DEFAULT_LEVEL) -> None:
    """Call once at startup.

    Args:
        debug: master switch. When False, every logger call is a no-op and
               nothing is opened or written.
        level: minimum severity to emit when debug is True. One of
               "ALL"|"DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL". "ALL" is an
               alias for "DEBUG" (everything kept).
    """
    global _debug_enabled, _log_file
    _debug_enabled = debug

    # Wipe any pre-existing handlers (defensive — supports re-init in tests).
    for h in list(_log.handlers):
        _log.removeHandler(h)

    if not debug:
        # Above CRITICAL — every isEnabledFor() check returns False, so the
        # logging machinery short-circuits before formatting. Effectively a
        # no-op for all logger.* calls.
        _log.setLevel(logging.CRITICAL + 1)
        return

    log_level = _resolve_level(level)
    _log.setLevel(log_level)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file = _LOG_DIR / f"{timestamp}.log"

    fmt_file = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    # The TUI handler formats with just the message — the sink prepends its
    # own coloured level glyph.
    fmt_tui = logging.Formatter("%(message)s")

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_log_file, mode="w", encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(fmt_file)
        _log.addHandler(fh)
    except OSError:
        pass

    # No stderr handler — Textual owns the terminal and stray writes corrupt
    # its rendering. The file + in-app debug window are the only sinks.

    th = _TUIHandler()
    th.setLevel(log_level)
    th.setFormatter(fmt_tui)
    _log.addHandler(th)

    _log.debug(
        "Debug logging enabled (level=%s). Log file: %s",
        logging.getLevelName(log_level),
        _log_file,
    )


def is_debug() -> bool:
    return _debug_enabled


def log_file() -> Path | None:
    """Path to the active debug log file, or None if --debug is off."""
    return _log_file


def register_tui_sink(callback: Callable[[str, str], None]) -> None:
    """Register a callback invoked for every log record (when --debug)."""
    global _tui_sink
    _tui_sink = callback


def unregister_tui_sink() -> None:
    global _tui_sink
    _tui_sink = None


def debug(msg: str, *args) -> None:
    _log.debug(msg, *args)


def info(msg: str, *args) -> None:
    _log.info(msg, *args)


def warning(msg: str, *args) -> None:
    _log.warning(msg, *args)


def error(msg: str, *args) -> None:
    _log.error(msg, *args)


def exception(msg: str, *args) -> None:
    _log.exception(msg, *args)


def file_only(msg: str, *args, level: int = logging.DEBUG) -> None:
    """Log to file but skip the TUI sink.

    Use when the caller has already written a styled message to the debug
    window directly and only wants the plain version persisted.
    """
    if not _debug_enabled:
        return
    if not _log.isEnabledFor(level):
        return
    record = _log.makeRecord(
        "termtube", level, "", 0, msg, args, None
    )
    setattr(record, _SKIP_TUI_ATTR, True)
    _log.handle(record)
