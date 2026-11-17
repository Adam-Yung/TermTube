# src/playlist.py

Local playlists: a JSON object `{name: [video_id, ...]}` in `<config dir>/playlists.json`. Playlists store ids only. Metadata comes from
the cache, and `Cache.pin_all_playlist_videos` (housekeeping) keeps playlist videos from being pruned.

## Rules

- Every call reads the file and every mutation rewrites it (`plat.atomic_write`). There is no in-memory cache and no
  lock, so callers are the UI thread (playlist modal) and the housekeeping worker reading only. Two writers at once would lose an update.
- A missing or corrupt file reads as empty.
- `add_video` creates the playlist if absent and returns `False` for a duplicate. Name order is creation order (dict order).
- `create` returns `False` and writes nothing when the name exists (it used to reset the playlist). The playlist modal reports it and adds nothing.
- No rename or delete: nothing in the UI uses them.

