"""YouTube page URLs."""

from __future__ import annotations


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
