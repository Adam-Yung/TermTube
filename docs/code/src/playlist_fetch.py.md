# src/playlist_fetch.py

The one reader of a YouTube playlist's or Mix's videos, shared by the playlist page (`ChannelPlaylistMixin`) and playback from a row (`PlaylistRowsMixin`). Blocking network calls: only workers call it.

- `page_fetcher(id)` picks `innertube.fetch_mix_page` for ids starting `RD` (a Mix: `browse` answers "unviewable", `next` serves it, endless) and `fetch_playlist_page` otherwise.
- `first_page` falls back to yt-dlp (`fetch_page_batch`, no continuation) when InnerTube returns nothing and gives no reason. A Mix has no yt-dlp reader.
- `fetch_videos` walks the continuations up to `channel_pager.MAX_ENTRIES` (a Mix never ends; the cap ends it) and de-duplicates, because a Mix continuation repeats rows. Errors propagate to the caller.
