"""Local playlists: name -> list of video ids, stored in `playlists.json`."""

from __future__ import annotations

from src.plat import get_config_dir
from src.store import JsonStore

_PLAYLISTS_PATH = get_config_dir() / "playlists.json"

_store = JsonStore(lambda: _PLAYLISTS_PATH, version=1, default=dict)


def list_names() -> list[str]:
    """Return all playlist names in creation order."""
    return _store.read(list)


def get_playlist(name: str) -> list[str]:
    """Return list of video IDs in the named playlist."""
    return _store.read(lambda data: list(data.get(name, [])))


def create(name: str, video_ids: list[str] | None = None) -> bool:
    """Create a playlist with the given video IDs. Returns False, changing nothing, if the name exists."""
    def apply(data: dict) -> bool:
        if name in data:
            return False
        data[name] = list(video_ids or [])
        return True

    return _store.update(apply)


def add_video(name: str, video_id: str) -> bool:
    """Add video_id to playlist, creating it if needed. Returns False if already present."""
    def apply(data: dict) -> bool:
        ids = data.setdefault(name, [])
        if video_id in ids:
            return False
        ids.append(video_id)
        return True

    return _store.update(apply)


def remove_video(name: str, video_id: str) -> bool:
    """Remove video_id from playlist. Returns False if not found."""
    def apply(data: dict) -> bool:
        if video_id not in data.get(name, []):
            return False
        data[name].remove(video_id)
        return True

    return _store.update(apply)


def is_in_playlist(name: str, video_id: str) -> bool:
    return _store.read(lambda data: video_id in data.get(name, []))


def video_playlists(video_id: str) -> list[str]:
    """Return names of all playlists containing video_id."""
    return _store.read(lambda data: [name for name, ids in data.items() if video_id in ids])


def add_videos(name: str, video_ids: list[str]) -> int:
    """Add the ids not yet in the playlist (created if needed), in order. Returns how many were added."""
    def apply(data: dict) -> int:
        ids = data.setdefault(name, [])
        fresh = [v for v in dict.fromkeys(video_ids) if v not in ids]
        ids.extend(fresh)
        return len(fresh)

    return _store.update(apply)
