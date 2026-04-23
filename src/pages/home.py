"""Home page — YouTube recommended feed."""

from __future__ import annotations
from src import ytdlp
from src.ui.fzf import run_list


def run(config, cache) -> str | None:
    """
    Show the YouTube home/recommended feed.
    Serves from disk cache instantly if fresh (TTL: home cache_ttl).
    Returns selected video_id or None (go back).
    """
    stream = ytdlp.stream_flat(
        ytdlp.FEED_URLS["home"],
        config,
        cache,
        feed_key="home",
    )
    return run_list(
        "🏠  Home — Recommended",
        stream,
        loading_msg="Fetching recommended feed…",
        preview_cols=config.thumbnail_cols,
        preview_rows=config.thumbnail_rows,
        config=config,
        cache=cache,
    )
