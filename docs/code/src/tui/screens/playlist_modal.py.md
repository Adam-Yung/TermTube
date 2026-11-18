# src/tui/screens/playlist_modal.py

Toggles a video's membership in playlists and creates playlists (`p`). Storage is `src/playlist.py`.

- `Space` selects the highlighted playlist (a yellow dot); `Enter` flips membership for every selected playlist at once, or for the
  highlighted one when none is selected. A green check marks current membership. `n` focuses the new-playlist input; a name that exists
  (any case) is refused with a notice.
- After every change `playlist.sync_pins` pins the entry's cached data and thumbnail while it is in some playlist and unpins it when it is in none.
