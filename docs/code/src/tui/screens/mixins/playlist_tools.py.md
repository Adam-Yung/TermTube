# src/tui/screens/mixins/playlist_tools.py

Playlist management on the Library tab, kept out of `MainScreen`. It uses `_current_tab`, `_list()`, `_selected_entry()`, `_hint`,
`_sync_player_bar` and the rail helpers of `LibraryRailMixin` (`_rail_focused`, `_rail_playlist`, `_select_collection`, `_collection_entries`).
With the rail focused the target is the playlist under the rail cursor; otherwise it is the playlist the list shows (`playlist:<id>`).

- `playlist_row(pl)` builds the one-row dict the delete question and rename read. `item_entries(pid, cache, config)` builds a playlist's list
  rows: a row title is the snapshot title; an item still without one (migrated from v1) is filled from the cache once, else it reads "Unknown
  video", never a bare id. With `config` each row gets its download state (`library.attach_local`: `_dl`, `_local_path`, ...), so playing a
  row uses the file on disk.
- `_playlist_removals()` feeds `MainScreen._removals()`: every `playlist:<id>` (items) plus `playlists`, used while the rail has focus
  (`_removal_key` / `_delete_targets` are overridden). On the rail `D` deletes the playlist under the cursor after a question that says the
  videos stay on disk (undo restores the record); inside a playlist `D` removes the marked or highlighted items from the playlist only (undo
  restores their positions). Pins are synced after each. `ListToolsMixin._after_removal` then refreshes the rail and leaves a deleted playlist.
- Keys (`keymap.PLAYLIST_TOOLS`): `n` new (Library tab; selects the new playlist), `R` rename, `J`/`K` move the highlighted video
  (saved at once; refused with a hint while a filter is on or at an end), `P`/`S`/`E` play / shuffle / queue the target playlist as audio
  through `AudioController.play_many` / `enqueue_many`. Outside the Library tab each key only says what to open.
- Names are asked with `NameModal`; a duplicate name (any case) is a hint and changes nothing.

The `Removal` callbacks are methods; the per-playlist ones are bound with the playlist id, so undo targets the playlist it removed from even after the view changed.
