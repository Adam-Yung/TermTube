"""TermTube v2 — local playlists.

Stores playlists in ~/.config/TermTube/playlists.json as:
  { "Playlist Name": ["video_id_1", "video_id_2", ...], ... }
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from config import PLAYLISTS_PATH

_lock = threading.Lock()


def _read() -> dict[str, list[str]]:
    try:
        return json.loads(PLAYLISTS_PATH.read_bytes())
    except Exception:
        return {}


def _write(data: dict[str, list[str]]) -> None:
    PLAYLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PLAYLISTS_PATH.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode())
    os.replace(tmp, PLAYLISTS_PATH)


def list_names() -> list[str]:
    return list(_read().keys())


def get_playlist(name: str) -> list[str]:
    return _read().get(name, [])


def create(name: str, ids: list[str] | None = None) -> None:
    with _lock:
        data = _read()
        if name not in data:
            data[name] = ids or []
            _write(data)


def delete(name: str) -> None:
    with _lock:
        data = _read()
        data.pop(name, None)
        _write(data)


def rename(old: str, new: str) -> None:
    with _lock:
        data = _read()
        if old in data:
            data[new] = data.pop(old)
            _write(data)


def add_video(name: str, video_id: str) -> None:
    with _lock:
        data = _read()
        lst = data.setdefault(name, [])
        if video_id not in lst:
            lst.append(video_id)
            _write(data)


def remove_video(name: str, video_id: str) -> None:
    with _lock:
        data = _read()
        if name in data:
            data[name] = [v for v in data[name] if v != video_id]
            _write(data)


def is_in_playlist(name: str, video_id: str) -> bool:
    return video_id in _read().get(name, [])


def video_playlists(video_id: str) -> list[str]:
    return [name for name, ids in _read().items() if video_id in ids]
