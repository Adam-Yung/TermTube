"""Logging for TermTube — file output only with --debug flag."""

from __future__ import annotations
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "TermTube"
_log = logging.getLogger("termtube")
_debug_enabled = False
_log_file: Path | None = None


def setup(debug: bool = False) -> None:
    """Call once at startup. With --debug, writes to a timestamped file in $TMPDIR/TermTube/."""
    global _debug_enabled, _log_file
    _debug_enabled = debug

    if not debug:
        _log.setLevel(logging.WARNING)
        return

    _log.setLevel(logging.DEBUG)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file = _LOG_DIR / f"{timestamp}.log"

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_log_file, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
        _log.addHandler(fh)
    except OSError:
        pass

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(logging.Formatter("\033[90m[DBG] %(message)s\033[0m"))
    _log.addHandler(sh)

    _log.debug("Debug logging enabled. Log: %s", _log_file)


def is_debug() -> bool:
    return _debug_enabled


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
