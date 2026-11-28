# src/tui/screens/mixins/playlist_rows.py

`v` `a` `e` on a playlist row, on both screens (`ItemActionsMixin` inherits it and calls `_use_playlist` first). Decisions: `docs/decisions/playlist-page.md`.

- `_playlist_source()` says what is under the cursor and how to load it. `PlaylistToolsMixin` overrides it for the Library rail, where the videos are local and read on the UI thread.
- Loading runs in the `playlist_row` worker group. Staleness is `AudioController.claim()` / `intent`: any later play, stop, previous or claim drops the result. A natural track change does not, so a playlist asked for near the end of a song still starts.
- A video run also needs the screen that asked to still be on top; audio starts wherever the user has gone.
- `_watch_run` chains one `WatchModal` per video through the dismiss result. It stops after three failures in a row: offline, every item would fail and each one asks YouTube three times.

`_on_run_item_done` gets the dismiss result of each player in a run.

- A folder row of the Local tab loads through `local_files.folder_tracks` (the media files directly inside, no network) and then plays like a playlist row.

- The `..` row (`_is_parent`) is refused for `v` `a` `e` with a hint: it stands for a folder that is not on screen.
