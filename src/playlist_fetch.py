"""Reads the videos of a YouTube playlist or Mix. No Textual: callers run it in a worker."""

from __future__ import annotations

from src import innertube, logger
from src.channel_pager import MAX_ENTRIES
from src.entries import Entry, PlaylistEntry, VideoEntry


def page_fetcher(playlist_id: str):
    """A Mix (``RD…``) is read through ``next``; every other playlist through ``browse``."""
    return innertube.fetch_mix_page if playlist_id.startswith("RD") else innertube.fetch_playlist_page


def first_page(row: PlaylistEntry, config, cache) -> innertube.ChannelPage:
    """InnerTube's first page; yt-dlp when it comes back empty without a reason."""
    import src.ytdlp as ytdlp

    playlist_id = row["id"]
    page = page_fetcher(playlist_id)(playlist_id)
    # With a reason from YouTube, or for a Mix (yt-dlp has no Mix reader), a second source would add nothing.
    if page.entries or (page.info or {}).get("unavailable") or playlist_id.startswith("RD"):
        return page
    logger.debug("InnerTube playlist empty; falling back to yt-dlp")
    url = row.get("url") or f"https://www.youtube.com/playlist?list={playlist_id}"
    return innertube.ChannelPage(ytdlp.fetch_page_batch(url, config, cache, count=MAX_ENTRIES))


def videos_only(entries: list[Entry]) -> list[VideoEntry]:
    """The rows that can be played, first occurrence of each id."""
    found = {
        e["id"]: e
        for e in entries
        if e.get("id") and not (e.get("_is_playlist") or e.get("_is_channel") or e.get("_missing_file"))
    }
    return list(found.values())


def fetch_videos(row: PlaylistEntry, config, cache) -> tuple[list[VideoEntry], str]:
    """The playlist's videos up to ``MAX_ENTRIES``, and YouTube's reason when it refuses to list them."""
    page = first_page(row, config, cache)
    reason = (page.info or {}).get("unavailable", "")
    entries, token = list(page.entries), page.token
    while token and len(entries) < MAX_ENTRIES:
        page = page_fetcher(row["id"])(row["id"], token)
        entries.extend(page.entries)
        token = page.token
    return videos_only(entries[:MAX_ENTRIES]), reason
