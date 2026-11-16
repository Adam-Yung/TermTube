"""Shapes of the row dicts that flow from loaders to the list, the detail panel and the audio queue.

Annotations only: rows stay plain dicts, and every key is optional because each source fills a different subset.
"""

from __future__ import annotations

from typing import TypedDict


class _Row(TypedDict, total=False):
    id: str
    title: str
    thumbnail: str
    uploader: str
    channel: str
    description: str
    webpage_url: str
    _type: str
    _is_playlist: bool
    _is_channel: bool
    _playlist_name: str
    _watched_at: float


class VideoEntry(_Row, total=False):
    """A video from InnerTube, yt-dlp, the history or the cache."""

    channel_id: str
    channel_url: str
    uploader_id: str
    uploader_url: str
    duration: int | None
    view_count: int | None
    like_count: int | None
    upload_date: str | None
    published_text: str
    view_count_text: str
    duration_text: str
    is_live: bool
    categories: list[str]
    keywords: list[str]
    _innertube: bool


class LibraryEntry(VideoEntry, total=False):
    """A downloaded video or audio file, read from its ``.info.json`` sidecar."""

    _local_path: str
    _local_type: str
    _has_audio: bool
    _audio_path: str | None
    _sidecar_path: str


class ChannelEntry(_Row, total=False):
    """A subscribed channel, or a channel row in a list."""

    channel_id: str
    channel_url: str
    uploader_url: str
    subscriber_count: int | None
    video_count: int | None


class PlaylistEntry(_Row, total=False):
    """A channel playlist (InnerTube or yt-dlp) or a local playlist row."""

    url: str
    playlist_count: int | None


Entry = VideoEntry | LibraryEntry | ChannelEntry | PlaylistEntry
