"""Worker-thread thumbnail resolution shared by the main, channel and detail-focus code."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from src.entries import Entry
from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE
from src.ui import thumbnail

_ANSI_CACHE_MAX = 64
_ansi_cache: OrderedDict[tuple[str, int, int], str] = OrderedDict()
_ansi_lock = threading.Lock()


def _cached_ansi(key: tuple[str, int, int]) -> str | None:
    with _ansi_lock:
        ansi = _ansi_cache.get(key)
        if ansi is not None:
            _ansi_cache.move_to_end(key)
        return ansi


def _store_ansi(key: tuple[str, int, int], ansi: str) -> None:
    with _ansi_lock:
        _ansi_cache[key] = ansi
        if len(_ansi_cache) > _ANSI_CACHE_MAX:
            _ansi_cache.popitem(last=False)


def load_thumbnail(
    app: Any,
    target: Any,
    vid: str,
    *,
    entry: Entry | None = None,
    url: str | None = None,
    cols: int = 38,
    rows: int = 20,
    is_current: Callable[[], bool],
) -> None:
    """Resolve a thumbnail and hand it to ``target``. Runs in a worker thread.

    ``target`` needs ``set_thumbnail_image``, ``set_thumbnail_ansi`` and
    ``set_thumbnail_placeholder``. ``is_current`` is polled after each slow step so a
    result for a row the cursor has already left is dropped.
    """
    if _HAS_TEXTUAL_IMAGE:
        path = thumbnail.ensure_thumb_jpeg(vid, entry, url=url)
        if not is_current():
            return
        if path and thumbnail.validate_thumb(path):
            app.call_from_thread(target.set_thumbnail_image, vid, path)
        else:
            app.call_from_thread(target.set_thumbnail_placeholder)
        return

    key = (vid, cols, rows)
    ansi = _cached_ansi(key)
    if ansi is None:
        ansi = thumbnail.render_pil_halfblock(
            vid, entry or {"id": vid, "thumbnail": url}, cols=cols, rows=rows
        )
        if ansi:
            _store_ansi(key, ansi)
    if not is_current():
        return
    if ansi:
        app.call_from_thread(target.set_thumbnail_ansi, vid, ansi)
    else:
        app.call_from_thread(target.set_thumbnail_placeholder)
