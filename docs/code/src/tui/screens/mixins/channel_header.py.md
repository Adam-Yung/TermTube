# src/tui/screens/mixins/channel_header.py

The channel page's left column and breadcrumb. `channel_screen.py.md` describes the page.

- `ch_info` worker fetches channel info; `ch_thumb` loads the avatar. The avatar has its own counter (`_info_avatar_session`), bumped only by `_apply_info`: it does not change with the cursor.
- A playlist page builds the same column from the playlist's header (`playlist_panel_info`) and remembers the owner for `o`.
- The avatar widget id comes from the channel or uploader id; without one the URL is sanitised, because the id names a cache file.
