"""Logging for MyYouTube — controlled by --debug flag."""

from __future__ import annotations
import logging
import sys
from pathlib import Path

_LOG_FILE = Path.home() / ".cache" / "myyoutube" / "debug.log"
_log = logging.getLogger("myt")
_debug_enabled = False


def setup(debug: bool = False) -> None:
    """Call once at startup with the --debug flag value."""
    global _debug_enabled
    _debug_enabled = debug

    _log.setLevel(logging.DEBUG if debug else logging.WARNING)

    if debug:
        # File handler — always write debug logs to file
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_LOG_FILE, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
        _log.addHandler(fh)

        # Stderr handler — show debug output on terminal
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG)
        sh.setFormatter(logging.Formatter("\033[90m[DBG] %(message)s\033[0m"))
        _log.addHandler(sh)

        _log.debug("Debug logging enabled. Log file: %s", _LOG_FILE)


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
