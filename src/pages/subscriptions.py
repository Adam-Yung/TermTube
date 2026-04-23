"""Subscriptions page — videos from subscribed channels."""

from __future__ import annotations
from src import ytdlp
from src.ui import fzf


def run(config, cache) -> str | None:
    """Show subscription feed. Returns selected video_id or None."""
    stream = ytdlp.stream_flat(
        ytdlp.FEED_URLS["subscriptions"],
        config,
        cache,
    )
    return fzf.run_list(
        "📺  Subscriptions",
        stream,
        loading_msg="Fetching subscription feed…",
        preview_cols=config.thumbnail_cols,
        preview_rows=config.thumbnail_rows,
    )
