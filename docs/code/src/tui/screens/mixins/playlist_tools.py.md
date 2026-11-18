# src/tui/screens/mixins/playlist_tools.py

Playlist management for the Playlists tab, kept out of `MainScreen` so it moves into the Library rail unchanged. It only uses
`_current_tab`, `_list()`, `_selected_entry()`, `_hint` and `_sync_player_bar`, and the views `playlists` (index) and `playlist:<id>`.

- `index_entries()` / `item_entries(pid, cache)` build list rows from `src/playlist.py` (the feed loader calls them too). A row title is the
  snapshot title; an item still without one (migrated from v1) is filled from the cache once, else it reads "Unknown video", never a bare id.
- `_playlist_removals()` feeds `MainScreen._removals()` (every existing `playlist:<id>` plus `playlists`, so `u` works after leaving a
  playlist). On the index `D` deletes playlists after a question that says the videos stay on disk (undo restores the record); inside a
  playlist `D` removes the marked or highlighted items from the playlist only (undo restores their positions). Pins are synced after each.
- Keys (`keymap.PLAYLIST_TOOLS`): `n` new (index only), `R` rename (highlighted or open playlist), `J`/`K` move the highlighted video
  (saved at once; refused with a hint while a filter is on or at an end), `P`/`S`/`E` play / shuffle / queue the open or highlighted
  playlist as audio through `AudioController.play_many` / `enqueue_many`. Outside the Playlists tab each key only says what to open.
- Names are asked with `NameModal`; a duplicate name (any case) is a hint and changes nothing.
