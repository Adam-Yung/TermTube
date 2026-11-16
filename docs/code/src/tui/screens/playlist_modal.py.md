# src/tui/screens/playlist_modal.py

Toggles a video's membership in playlists and creates playlists. Storage is `src/playlist.py`.

- Adding a video pins its cached data and thumbnail (`cache.pin_video`, `pin_thumb`) so cache eviction cannot drop playlist entries. Removing it from its last playlist unpins.
- Selecting a row toggles; `n` focuses the new-playlist input.
