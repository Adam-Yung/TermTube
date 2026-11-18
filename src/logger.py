"""Debug logging. Off by default: the logger sits above CRITICAL, so every call is a no-op.

With --debug it writes a timestamped file in the temp dir and mirrors to the TUI sink.
Never stderr (it corrupts Textual's rendering).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from src.plat import get_log_dir, private_dir

DEFAULT_LEVEL = "ALL"  # alias for DEBUG


def _resolve_level(name: str) -> int:
    upper = (name or "").upper()
    if upper in ("", "ALL"):
        return logging.DEBUG
    return getattr(logging, upper, logging.DEBUG)


_LOG_DIR = get_log_dir()
_log = logging.getLogger("termtube")
_log.propagate = False
_debug_enabled = False
_log_file: Path | None = None
_t_import = time.monotonic()
_t_last = _t_import
_stages_seen: set[str] = set()

# Set on records the screen already rendered into the debug window itself.
_SKIP_TUI_ATTR = "_termtube_skip_tui"

_tui_sink: Callable[[str, str], None] | None = None


_URL_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+)\?[^\s'\"<>]*")
_SECRET = re.compile(
    r"(?i)\b(cookie|set-cookie|sapisid\w*|__secure-\w+|access_token|token|signature|sig)\b(\s*[=:]\s*)[^\s,;'\"]+"
)
_AUTH_HEADER = re.compile(r"(?i)\b(authorization\s*[=:]\s*)[^\n]+")  # "Scheme value": two words
_MAX_LINE = 2000


def redact(text: str) -> str:
    """Strip URL query strings (signed stream URLs), cookie/token values and runaway length from a log line."""
    text = _URL_QUERY.sub(r"\1?<redacted>", text)
    text = _AUTH_HEADER.sub(r"\1<redacted>", text)
    text = _SECRET.sub(r"\1\2<redacted>", text)
    return text if len(text) <= _MAX_LINE else text[:_MAX_LINE] + "…"


class _RedactFilter(logging.Filter):
    """Redacts the message and any traceback of a record before a handler writes it (yt-dlp errors embed URLs)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = redact(record.getMessage()), None
        if record.exc_info:
            record.exc_text = redact("".join(logging.Formatter().formatException(record.exc_info)))
            record.exc_info = None
        return True


class _TUIHandler(logging.Handler):
    """Forwards records to the registered TUI sink."""

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, _SKIP_TUI_ATTR, False):
            return
        sink = _tui_sink
        if sink is None:
            return
        try:
            sink(record.levelname, self.format(record))
        except Exception:
            pass


def setup(debug: bool = False, level: str = DEFAULT_LEVEL) -> None:
    """Call once at startup. level only applies when debug is True."""
    global _debug_enabled, _log_file
    _debug_enabled = debug
    _stages_seen.clear()

    for h in list(_log.handlers):
        _log.removeHandler(h)

    if not debug:
        _log.setLevel(logging.CRITICAL + 1)
        return

    log_level = _resolve_level(level)
    _log.setLevel(log_level)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file = _LOG_DIR / f"{timestamp}.log"

    fmt_file = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    # The sink prepends its own level glyph, so format the message only.
    fmt_tui = logging.Formatter("%(message)s")

    try:
        private_dir(_LOG_DIR)
        fh = logging.FileHandler(_log_file, mode="w", encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(fmt_file)
        fh.addFilter(_RedactFilter())
        _log.addHandler(fh)
    except OSError:
        pass

    th = _TUIHandler()
    th.setLevel(log_level)
    th.setFormatter(fmt_tui)
    th.addFilter(_RedactFilter())
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


def register_tui_sink(callback: Callable[[str, str], None] | None) -> None:
    """Register a callback invoked for every log record (when --debug); None unregisters it.

    It runs under the logging handler lock, from any thread: it must not block.
    """
    global _tui_sink
    _tui_sink = callback


def stage(name: str) -> None:
    """Log a startup milestone once, with the time since the previous one and since this module loaded."""
    global _t_last
    if not _debug_enabled or name in _stages_seen:
        return
    _stages_seen.add(name)
    now = time.monotonic()
    _log.debug(
        "startup stage %s: +%.0f ms (%.0f ms since start)", name, (now - _t_last) * 1000, (now - _t_import) * 1000
    )
    _t_last = now


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
    """Log to the file only, for messages already drawn in the debug window."""
    if not _debug_enabled:
        return
    if not _log.isEnabledFor(level):
        return
    record = _log.makeRecord(
        "termtube", level, "", 0, msg, args, None
    )
    setattr(record, _SKIP_TUI_ATTR, True)
    _log.handle(record)
