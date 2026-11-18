# src/tui/screens/mixins/library_rail.py

The Library tab's rail logic, split from `MainScreen`. The rail picks which collection the one `VideoListPanel` shows; a pick is an ordinary
`_load_view` (so the feed session guard, paging, filter, marks, `D` and `u` work unchanged). `tab_of(view)` maps `library`, `library:video`,
`library:audio` and `playlist:<id>` to the `library` tab.

- `_current_tab` holds the shown collection; `_library_view` remembers it for when the user leaves the tab and comes back.
- Rail entries: three fixed collections with counts (`_library_counts`, refreshed by every Library load and after a removal), one entry per
  playlist (count of its items), `+ New playlist` (`NEW_PLAYLIST`; Enter on it calls `action_playlist_new`).
- Focus: `Tab` (`action_rail_toggle`) flips between rail and list; it is ignored while the filter bar has focus. The rail's own bindings take
  `j k g G Enter l`; `OWNS_NAV_KEYS` stops `ListNavMixin.on_key` from pulling focus back to the list.
- `action_page_prev` overrides the list's `h`: on the first page of a Library list it moves focus to the rail instead of paging.
- `_after_removal` recounts and, when the shown playlist is gone, falls back to All downloads without taking focus from the rail.
- Narrow terminals: `on_resize` collapses the rail to a docked one-line selector below `NARROW_BELOW` columns (same keys: `Tab`, `j`/`k`, `Enter`).
- `_collection_entries(view)` is called from loader threads too: it only reads the Library index and `playlists.json`.
- `ACCOUNT_VIEWS` maps account-backed History sources (`history:yt`, `history:wl`) to their feed keys and `HISTORY_SOURCES` lists every source of the History tab (`history` is Local); `tab_of` maps them all to `history`, so the tab bar stays on History. `MainScreen._history_view` remembers the source across tab switches.
