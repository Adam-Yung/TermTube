"""Search page — prompt for query, stream results into fzf."""

from __future__ import annotations
from src import ytdlp
from src.ui import fzf, gum


def run(config, cache, *, initial_query: str | None = None) -> str | None:
    """
    Prompt user for a search query, then show results.
    Returns selected video_id or None.
    """
    query = initial_query or fzf.prompt_search("Search YouTube…")
    if not query:
        return None

    stream = ytdlp.stream_search(query, config, cache)

    return fzf.run_list(
        f"🔍  Search: {query}",
        stream,
        loading_msg=f'Searching for "{query}"…',
        preview_cols=config.thumbnail_cols,
        preview_rows=config.thumbnail_rows,
        config=config,
        cache=cache,
    )
