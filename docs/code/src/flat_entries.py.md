# src/flat_entries.py

Shapes yt-dlp's flat listing entries into rows. Split from `src/ytdlp.py`; callers are `ytdlp.py`, `src/feed_cursor.py` and
`scripts/owner/probe-home.py`. No yt-dlp import and no network.

- `FlatBatch` is the one collector of a fetch (used by `ytdlp._extract_videos` and `FeedCursor.take`): drop skipped ids, `cache.put_video`,
  record the id, and fire `on_first_batch` once. A cursor passes its own `ids` list so it spans batches.
- `is_playable_video` accepts only an 11-character video id that is not a playlist or channel row.
- `playlist_row(entry)` is the one place a flat entry becomes a playlist or Mix list row on Home (`_is_playlist`, `_playlist_name`, `url`,
  thumbnail); `FeedCursor(playlists=True)` calls it before `is_playable_video`.
- `best_thumb_url` is imported inside the functions: `src.ui.thumbnail` imports the cache, which creates its directories at import.
