"""Playlist management — stored as JSON at ~/.local/share/termtube/playlists.json."""

from __future__ import annotations
import json
from pathlib import Path

_PLAYLISTS_PATH = Path.home() / ".config" / "TermTube" / "playlists.json"


def _load() -> dict[str, list[str]]:
    if _PLAYLISTS_PATH.exists():
        try:
            return json.loads(_PLAYLISTS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict[str, list[str]]) -> None:
    _PLAYLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLAYLISTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def list_names() -> list[str]:
    """Return all playlist names in creation order."""
    return list(_load().keys())


def get_playlist(name: str) -> list[str]:
    """Return list of video IDs in the named playlist."""
    return list(_load().get(name, []))


def create(name: str, video_ids: list[str] | None = None) -> None:
    """Create a playlist (or reset existing) with the given video IDs."""
    data = _load()
    data[name] = list(video_ids or [])
    _save(data)


def delete(name: str) -> bool:
    """Delete a playlist. Returns False if it didn't exist."""
    data = _load()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


def add_video(name: str, video_id: str) -> bool:
    """Add video_id to playlist, creating it if needed. Returns False if already present."""
    data = _load()
    if name not in data:
        data[name] = []
    if video_id in data[name]:
        return False
    data[name].append(video_id)
    _save(data)
    return True


def remove_video(name: str, video_id: str) -> bool:
    """Remove video_id from playlist. Returns False if not found."""
    data = _load()
    if name not in data or video_id not in data[name]:
        return False
    data[name].remove(video_id)
    _save(data)
    return True


def rename(old_name: str, new_name: str) -> bool:
    """Rename a playlist. Returns False if old_name doesn't exist."""
    data = _load()
    if old_name not in data:
        return False
    # Preserve insertion order by rebuilding
    new_data = {(new_name if k == old_name else k): v for k, v in data.items()}
    _save(new_data)
    return True


def is_in_playlist(name: str, video_id: str) -> bool:
    return video_id in _load().get(name, [])


def video_playlists(video_id: str) -> list[str]:
    """Return names of all playlists containing video_id."""
    return [name for name, ids in _load().items() if video_id in ids]
