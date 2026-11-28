"""Channels the user follows locally: ``channels.json``, so it works with ``browser: none``."""

from __future__ import annotations

import time
from functools import partial

from src.channel_ref import is_channel_id
from src.entries import ChannelEntry
from src.plat import get_config_dir
from src.store import JsonStore

CHANNELS_PATH = get_config_dir() / "channels.json"

_store = JsonStore(lambda: CHANNELS_PATH, version=1, default=list)


def toggle(channel_id: str, name: str, avatar: str = "") -> bool:
    """Follow the channel if it is not followed, else unfollow it. Returns True when it is now followed.

    A value that is not a ``UC…`` id is refused (returns False, nothing stored).
    """
    if not is_channel_id(channel_id):
        return False
    return _store.update(partial(_toggle, channel_id=channel_id, name=name, avatar=avatar)) == "followed"


def _toggle(data: list, channel_id: str, name: str, avatar: str) -> str:
    """Both outcomes are non-empty, so the store saves either way."""
    for record in data:
        if record["id"] == channel_id:
            data.remove(record)
            return "unfollowed"
    data.append({"id": channel_id, "name": name, "avatar": avatar, "added": time.time()})
    return "followed"


def entries() -> list[ChannelEntry]:
    """Followed channels as list rows, newest follow first."""
    records = sorted(_store.read(list), key=lambda c: c.get("added", 0), reverse=True)
    return [
        {
            "id": c["id"],
            "title": c["name"],
            "channel": c["name"],
            "uploader": c["name"],
            "channel_id": c["id"],
            "channel_url": f"https://www.youtube.com/channel/{c['id']}",
            "thumbnail": c.get("avatar", ""),
            "_type": "channel",
            "_is_channel": True,
        }
        for c in records
    ]
