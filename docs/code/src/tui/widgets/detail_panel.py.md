# src/tui/widgets/detail_panel.py

Right-hand panel: `ThumbnailWidget`, title/channel/stats/description, playlist membership, and the `ActionBar`. It is a passive view (`docs/decisions/thumbnails.md`, "DetailPanel as a passive view"): it starts no workers and fetches nothing. The owning screen paints it through `update_basic`, `refresh_metadata`, `update_channel_entry` and the `set_thumbnail_*` proxies.

## Invariants

- `current_id` is the id of the row the panel shows. Async results (`refresh_metadata`, thumbnails) are dropped when their id differs, which is how a late worker result is kept from overwriting a newer row. `ThumbnailWidget` keeps its own id for the same purpose.
- `update_basic` shows "Loading…" for the description only for real video ids (not `__playlist__...` placeholders) that lack a description.
- The channel link is `[@click=screen.channel]`. The `screen.` prefix resolves `action_channel` on the screen (`ItemActionsMixin`), which opens the channel of the highlighted row. The panel has no channel action of its own.
- `set_channel_mode` (Subscriptions tab) hides the action bar and reuses the same Statics for channel name, subscriber/video counts, URL and description. `set_video_mode` restores it. `FeedLoaderMixin._load_view` resets to video mode on every tab except Subscriptions.
- `on_resize` (debounced 150 ms) and `on_screen_resume` post `RerenderRequested`. The screen re-renders the thumbnail at the new cell size (`DetailFocusMixin.on_detail_panel_rerender_requested`). The half-block fallback needs this; textual-image scales itself.

## Limits

`thumbnail_cell_size` falls back to 38x20 before layout. A thumbnail rendered at that size is wrong until the first resize event corrects it.

Library rows show a `#video-file` line: path relative to the download folder and total size (`library.total_size`), or `⚠ file missing`.

`refresh_playlists` shows "In playlists: A, B" for any video that is in a playlist.
