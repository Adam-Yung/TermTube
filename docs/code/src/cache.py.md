# src/cache.py

Disk cache under the platform cache dir: video metadata JSON, feed id lists, suppression state, the home quick-start stash, thumbnails, and pinned playlist copies. Callers: feed loader and fetchers (`src/ytdlp.py`), detail panel, playlist modal, `src/tui/app.py` (startup pruning). History: `docs/decisions/feeds-and-paging.md`, `docs/decisions/thumbnails.md`.

## Layout

- `videos/<id>.json`: slim yt-dlp entry plus `_cached_at`. `_FAT_FIELDS` (formats, subtitles, heatmap, ...) are stripped on write: about 48 KB becomes about 2 KB.
- `feed_<key>.json`: `{ids, format, _cached_at}`; a file whose `format` is not `FEED_FORMAT` (2: Home rows may be playlists and Mixes) counts as missing, so a cache written before that is refetched once; TTL from the `ttl_map` given to `Cache` (default 1 h). Search feeds use key `search_<hash>`.
- `feed_home_stash.json`: up to 20 full entries saved at exit so the next boot shows content at once.
- `playlist_videos/`, `playlist_thumbs/`: copies of playlist members. Pruning only touches `videos/` and `thumbs/`, so a pinned video survives eviction. `pin_video` takes the entry the caller holds (the playlist modal passes the row it was opened on, so a video that is no longer in `videos/` still pins) and strips the fat fields like `put_video`.
- `suppressed.json`: ids hidden from the home feed, with focus counts.

## Invariants

- Writes go through `_atomic_write` (`plat.atomic_write` with failures swallowed) under one module-wide `_write_lock`, because enrichment threads write concurrently. Readers never see partial files. A write that fails is dropped silently.
- A 64-entry in-memory LRU fronts `videos/`. `get_video` honors the `metadata` TTL; `get_video_raw` ignores it and falls back to the pinned copy, which is what feed rebuilds and the library use.
- Pruning uses file mtime as age. That is valid because `put_video` always rewrites the file.
- A video is suppressed on its third focus (`register_focus`) or immediately (`suppress_video`). Focus counts live in memory and are flushed only when a suppression happens, so cursor movement does no disk I/O. Caps: 5000 focus counts, and suppressed ids trim from 2000 to 1500, oldest first.
- Suppression state loads lazily, once per process, under `_suppression_lock`.

## Limits

- `clear_all` removes feeds, videos and thumbnails (and the RAM copies, so a cleared video is not served back) but leaves the stash, suppression state and pinned playlist copies. It returns the file count for the Settings "Clear cache" message.
- No cross-process locking: two TermTube instances can interleave writes (each write stays atomic; last writer wins).

`pin_thumb(video_id, source=None)` pins `source` (a downloaded file's normalised JPEG) when given, else the cached thumbnail. The download modal pins every finished download with `pin_video` (public fields only) and `pin_thumb`.

- `feed_age(key)` is the seconds since the feed id list was written, or None when missing or past its TTL (Home revalidation compares it with `cache_ttl.home_revalidate`).
