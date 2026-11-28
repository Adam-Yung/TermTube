# src/tui/screens/mixins/library_rail.py

The side-list logic of the Library, History and Subscriptions tabs (`RAIL_TABS`), split from `MainScreen`. The rail picks which source the one `VideoListPanel` shows; a pick is an ordinary
`_load_view` (so the feed session guard, paging, filter, marks, `D` and `u` work unchanged). `tab_of(view)` maps `library`, `library:video`,
`library:audio` and `playlist:<id>` to the `library` tab, the History sources to `history`, and `subscriptions` / `following` to `subscriptions`.

- `_current_tab` holds the shown source; `_rail_views` (tab to source) remembers each tab's source for when the user leaves the tab and comes back. Every tab opens on its first entry (Library: All downloads, History: TermTube history, Subscriptions: Subscribed).
- Rail entries by tab. History: `history` (with the local count), `history:yt`, `history:wl`. Subscriptions: `subscriptions`, `following` (the breadcrumb is set in `_select_collection`). Library: three fixed collections with counts (`_library_counts`, refreshed by every Library load and after a removal), one entry per
  playlist (count of its items), `+ New playlist` (`NEW_PLAYLIST`; Enter on it calls `action_playlist_new`).
- Focus: `Tab` (`action_rail_toggle`) flips between rail and list; it is ignored while the filter bar has focus. The rail's own bindings take
  `j k g G Enter l`; `OWNS_NAV_KEYS` stops `ListNavMixin.on_key` from pulling focus back to the list.
- `action_page_prev` overrides the list's `h`: on the first page of a list with a rail it moves focus to the rail instead of paging.
- `_after_removal` recounts and, when the shown playlist is gone, falls back to All downloads without taking focus from the rail.
- Narrow terminals: `on_resize` collapses the rail to a docked one-line selector below `NARROW_BELOW` columns (same keys: `Tab`, `j`/`k`, `Enter`).
- `_collection_entries(view)` is called from loader threads too: it only reads the Library index and `playlists.json`.
- `ACCOUNT_VIEWS` maps account-backed History sources (`history:yt`, `history:wl`) to their feed keys and `HISTORY_SOURCES` lists every source of the History tab (`history` is Local); `tab_of` maps them all to `history`, so the tab bar stays on History. The rail replaced the `Y` source cycle and the `F` Following key, so there is one way to switch sources on every tab.

View ids and `tab_of` are defined in `tui/views.py`. Each rail tab has its own item builder.
