"""Turns yt-dlp's flat listing entries into TermTube rows, and collects the playable ones of one batch."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable

from src.cache import Cache
from src.entries import ChannelEntry, PlaylistEntry, VideoEntry

_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def is_playable_video(entry: VideoEntry) -> bool:
    """A flat entry with an 11-character video id (anything else, including a malformed row, is skipped)."""
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not _VIDEO_ID_RE.match(entry["id"]):
        return False
    return entry.get("_type", "video") not in ("playlist", "channel")


_LIST_PARAM_RE = re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/playlist\?(?:.*&)?list=([\w-]+)")


def playlist_row(entry: dict) -> dict | None:
    """A flat Home entry that is a playlist or Mix (yt-dlp: ``ie_key`` ``YoutubeTab``, a ``playlist?list=`` url) as a
    list row, or None for anything else. Home only: the other account feeds list videos."""
    if not isinstance(entry, dict) or entry.get("ie_key") != "YoutubeTab":
        return None
    match = _LIST_PARAM_RE.match(str(entry.get("url") or ""))
    if not match:
        return None
    playlist_id = match.group(1)
    row = {k: v for k, v in entry.items() if k not in ("ie_key",)}
    row.update(
        id=playlist_id, url=f"https://www.youtube.com/playlist?list={playlist_id}", _is_playlist=True, _type="playlist"
    )
    row["webpage_url"] = row["url"]
    row["_playlist_name"] = row.get("title") or ""
    if not row.get("thumbnail"):
        from src.ui.thumbnail import best_thumb_url
        row["thumbnail"] = best_thumb_url(row) or ""
    return row


def normalise_entry(entry: VideoEntry) -> VideoEntry:
    """Ensure flat-playlist entries have 'thumbnail' and 'webpage_url' fields."""
    entry.setdefault("webpage_url", f"https://www.youtube.com/watch?v={entry.get('id', '')}")
    if not entry.get("thumbnail"):
        from src.ui.thumbnail import best_thumb_url
        url = best_thumb_url(entry)
        if url:
            entry["thumbnail"] = url
    return entry


class FlatBatch:
    """The entries of one fetch: caches each new one and reports the first ``first_batch_size`` early, once.

    ``ids`` may be a list the caller keeps across batches; every accepted id is appended to it.
    """

    def __init__(
        self,
        cache: Cache,
        skip_ids: set[str],
        on_first_batch: Callable[[list[VideoEntry]], None] | None,
        first_batch_size: int,
        ids: list[str] | None = None,
    ) -> None:
        self.entries: list[VideoEntry] = []
        self.ids: list[str] = [] if ids is None else ids
        self._cache, self._skip_ids = cache, skip_ids
        self._on_first_batch, self._first_batch_size = on_first_batch, first_batch_size

    def add(self, entry: VideoEntry) -> bool:
        """Take a shaped entry unless its id is to be skipped. True when it was taken."""
        vid = entry.get("id", "")
        if vid in self._skip_ids:
            return False
        self._cache.put_video(entry)
        self.ids.append(vid)
        self.entries.append(entry)
        if self._on_first_batch and len(self.entries) == self._first_batch_size:
            self._on_first_batch(list(self.entries))
            self._on_first_batch = None
        return True

    def read(self, info: dict, count: int, cancel: threading.Event) -> None:
        """Add the playable entries of a flat listing until the batch holds ``count`` or ``cancel`` is set."""
        for entry in (info.get('entries') or []):
            if cancel.is_set() or len(self.entries) >= count:
                return
            if is_playable_video(entry):
                self.add(normalise_entry(entry))


def collect_channel_playlists(rows: list[PlaylistEntry], info: dict, count: int, cancel: threading.Event) -> None:
    """Add the playlists of a channel's listing to ``rows``, up to ``count`` or until ``cancel`` is set.

    The listing is lazy and may raise part way; ``rows`` keeps what was read.
    """
    for entry in (info.get('entries') or []):
        if cancel.is_set() or len(rows) >= count:
            break
        row = _channel_playlist_row(entry)
        if row is not None:
            rows.append(row)


def _channel_playlist_row(entry: dict | None) -> dict | None:
    """A row of a channel's Playlists listing, marked as a playlist; None for what is not one."""
    if entry is None:
        return None
    if entry.get("_type", "") not in ("playlist", "url") and not entry.get("id"):
        return None
    normalise_entry(entry)
    pid = entry.get("id", "")
    if pid:
        entry.setdefault("_is_playlist", True)
        entry.setdefault("_playlist_name", entry.get("title", pid))
    return entry


def subscribed_channel_row(data: dict | None) -> ChannelEntry | None:
    """One entry of the subscriptions channel list as a channel row, or None without an id."""
    if data is None:
        return None
    cid = data.get("id") or data.get("channel_id") or ""
    if not cid:
        return None
    name = data.get("title") or data.get("channel") or data.get("uploader") or cid
    ch_url = data.get("url") or data.get("channel_url") or ""
    return {
        "id": cid, "title": name, "channel": name,
        "channel_url": ch_url, "channel_id": cid,
        "uploader": name, "uploader_url": ch_url,
        "subscriber_count": data.get("channel_follower_count"),
        "video_count": data.get("playlist_count"),
        "thumbnail": data.get("thumbnail") or "",
        "description": data.get("description") or "",
        "_is_channel": True,
    }


def _avatar_url(data: dict) -> str:
    """The uncropped avatar, else the last thumbnail."""
    thumbs = data.get("thumbnails") or []
    url = next((t.get("url", "") for t in reversed(thumbs) if t.get("id") == "avatar_uncropped"), "")
    if url:
        return url
    return thumbs[-1].get("url", "") if thumbs else data.get("thumbnail", "")


def channel_info_row(data: dict, channel_url: str) -> dict:
    """The channel header from yt-dlp's channel listing."""
    return {
        "channel_url": channel_url,
        "channel": data.get("channel") or data.get("uploader") or data.get("title", ""),
        "channel_id": data.get("channel_id") or data.get("uploader_id", ""),
        "description": data.get("description", ""),
        "subscriber_count": data.get("channel_follower_count"),
        "thumbnail": _avatar_url(data),
        "uploader_url": data.get("uploader_url", ""),
    }
