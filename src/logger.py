"""Logging for TermTube.

Behaviour:
  • Without --debug: the logger is set above CRITICAL — every logger.* call is a
    fast no-op (the level check happens before any formatting). No files are
    opened, no handlers attached, nothing is written.
  • With --debug: writes to a timestamped file in $TMPDIR/TermTube/, mirrors to
    stderr, and (if a TUI sink is registered via register_tui_sink) mirrors to
    the in-app debug window.

Public API:
  setup(debug)            — call once at startup
  is_debug()              — bool
  debug/info/warning/error/exception(msg, *args) — standard log calls
  file_only(msg, *args)   — write to file/stderr only, skip TUI sink. Used by
                            UI code that has already drawn a styled message
                            into the debug window itself.
  register_tui_sink(cb)   — cb(level: str, formatted_msg: str) is invoked from
                            inside the logger thread for each emitted record.
                            The callback is responsible for thread-safety
                            (e.g. App.call_from_thread).
  unregister_tui_sink()
"""

from __future__ import annotations
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

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


def setup(debug: bool = False) -> None:
    """Call once at startup."""
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

    _log.setLevel(logging.DEBUG)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file = _LOG_DIR / f"{timestamp}.log"

    fmt_file = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    fmt_stderr = logging.Formatter("\033[90m[DBG] %(message)s\033[0m")
    # The TUI handler formats with just the message — the sink prepends its
    # own coloured level glyph.
    fmt_tui = logging.Formatter("%(message)s")

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_log_file, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt_file)
        _log.addHandler(fh)
    except OSError:
        pass

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt_stderr)
    _log.addHandler(sh)

    th = _TUIHandler()
    th.setLevel(logging.DEBUG)
    th.setFormatter(fmt_tui)
    _log.addHandler(th)

    _log.debug("Debug logging enabled. Log file: %s", _log_file)


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
    """Log to file/stderr but skip the TUI sink.

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
