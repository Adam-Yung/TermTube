"""Subscriptions page — videos from subscribed channels."""

from __future__ import annotations
from src import ytdlp
from src.ui.fzf import run_list


def run(config, cache) -> str | None:
    """
    Show subscription feed.
    Serves from disk cache instantly if fresh (TTL: subscriptions cache_ttl).
    Returns selected video_id or None.
    """
    stream = ytdlp.stream_flat(
        ytdlp.FEED_URLS["subscriptions"],
        config,
        cache,
        feed_key="subscriptions",
    )
    return run_list(
        "📺  Subscriptions",
        stream,
        loading_msg="Fetching subscription feed…",
        preview_cols=config.thumbnail_cols,
        preview_rows=config.thumbnail_rows,
        config=config,
        cache=cache,
    )
