# src/playlist.py

Local playlists: a JSON object `{name: [video_id, ...]}` in `<config dir>/playlists.json`. Playlists store ids only. Metadata comes from
the cache, and `Cache.pin_all_playlist_videos` (housekeeping) keeps playlist videos from being pruned.

## Rules

- Storage is a `store.JsonStore` (version 1, data shape `{name: [ids]}`, see [store.py.md](store.py.md)). Every mutation is one
  `update` under the store's lock, so the playlist modal and the housekeeping worker cannot lose each other's change.
- A missing file reads as empty; a corrupt one is kept as `playlists.json.bad` and reads as empty.
- `add_video` creates the playlist if absent and returns `False` for a duplicate. Name order is creation order (dict order).
- `create` returns `False` and writes nothing when the name exists (it used to reset the playlist). The playlist modal reports it and adds nothing.
- No rename or delete: nothing in the UI uses them.

