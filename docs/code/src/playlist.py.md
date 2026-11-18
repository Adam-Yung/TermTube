# src/playlist.py

Local playlists (v2) in `<config dir>/playlists.json`: `{"playlists": [{"id": "pl_xxxx", "name", "created", "updated", "kind": "manual",
"items": [{"id", "title", "uploader", "duration", ..., "added"}]}]}` inside the `JsonStore` envelope (version 2, see [store.py.md](store.py.md)).
Items are slim snapshots (the same slimmer as history, `history.slim`), so a playlist row never needs the cache to show a title.

## Rules

- Every call is one `read` or `update` under the store lock; two threads cannot lose each other's change. Reads return deep copies.
- Playlists are addressed by **id**; the name is a label. Names are unique case-insensitively (`create` and `rename` return `None` / `False`
  and change nothing otherwise; renaming to the same name in another case is allowed).
- **Migration v1 to v2** (`_migrate`, run by the store on first load of an old file): `{name: [ids]}` becomes records with fresh ids. The old
  file is copied to `playlists.json.v1` first, once, never overwriting an existing backup. Odd input is tolerated: non-dict file gives no
  playlists, non-list values give empty playlists, non-string ids and blank names are dropped, duplicate ids inside a playlist collapse,
  names that differ only by case become `Name (2)`, `Name (3)`. Migrated items have an empty title; `item_entries` fills them from the cache
  on first open (`refresh_items`). A corrupt file is kept as `playlists.json.bad`.
- `add_items` appends new ids and *refreshes* known ones (fills empty snapshot fields only; richer data never overwrites a title).
- `remove_items` returns the removed items with their old index in `_pos`; `restore_items` puts them back there (clamped) and strips `_pos`.
- `move_item(pid, vid, to)` is False, changing nothing, when `to` is out of range or the video is absent.
- `transfer(src, dst, ids, move=...)` copies or moves between playlists; videos already in `dst` are not duplicated.
- `delete` returns the record so `restore` can bring it back (undo); `restore` refuses when the id or name is taken again.
- `sync_pins(cache, ids, entries)` is the one place that keeps the cache consistent: ids still in some playlist are pinned (video JSON and
  thumbnail), the others unpinned. Callers pass the ids a change touched, after the change.
- Deleting a playlist or an item never touches downloaded files.
