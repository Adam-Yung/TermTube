"""Reads a YouTube channel URL: the one place that knows its path forms."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_ID = re.compile(r"UC[\w-]{22}")
_FORMS = (
    ("id", re.compile(r"^/channel/(UC[\w-]{22})(?:/|$)")),
    ("handle", re.compile(r"^/(@[^/\s]+)(?:/|$)")),
    ("c", re.compile(r"^/c/([^/\s]+)(?:/|$)")),
    ("user", re.compile(r"^/user/([^/\s]+)(?:/|$)")),
)


def parse(url: str) -> tuple[str, str] | None:
    """``(form, value)`` for a channel URL, or None. ``form`` is ``id``, ``handle``, ``c`` or ``user``."""
    path = urlparse(url.strip()).path
    for form, pattern in _FORMS:
        match = pattern.match(path)
        if match:
            return form, match.group(1)
    return None


def channel_id(url: str) -> str | None:
    """The ``UC…`` id when the URL carries it (``/channel/UC…``); handles and legacy names need a lookup."""
    parsed = parse(url)
    return parsed[1] if parsed and parsed[0] == "id" else None


def is_channel_id(value: str) -> bool:
    return bool(_ID.fullmatch(value))
