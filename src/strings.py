"""User-facing text: every notice, prompt, label and hint the UI shows lives in ``strings.json``, looked up by key."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def _flatten(prefix: str, node: dict, flat: dict[str, str]) -> None:
    for name, value in node.items():
        key = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            _flatten(key, value, flat)
        else:
            flat[key] = value


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    """``strings.json`` flattened to dotted keys: ``{"item": {"live": "x"}}`` becomes ``{"item.live": "x"}``."""
    flat: dict[str, str] = {}
    _flatten("", json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8")), flat)
    return flat


def text(key: str, **values: object) -> str:
    """The string for ``key`` with ``{name}`` placeholders filled from ``values``. A missing key raises ``KeyError``."""
    return _table()[key].format(**values) if values else _table()[key]
