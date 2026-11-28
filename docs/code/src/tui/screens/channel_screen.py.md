# src/tui/screens/channel_screen.py

The screen keeps composition, tabs, key actions and `_call_ui`. The left column and breadcrumb are `ChannelHeaderMixin`; loading, fetching and paging are `ChannelContentMixin`; tab ids and labels are `channel_tabs.py`.

Pushed on top of `MainScreen` for one channel: info column (`ChannelInfoPanel`), a tab bar (Videos, Shorts, Live, Playlists) and list in the middle, `DetailPanel` on the right. It reuses `ListNavMixin`, `DetailFocusMixin` and `ItemActionsMixin`; it has no audio of its own (`AudioBarMixin` mirrors `app.audio`).

## Audio

Audio keys act on `app.audio`, so music keeps playing across channel pages and this screen never scans the screen stack. `AudioBarMixin` shows the state:

- `on_mount` calls `_sync_player_bar` to copy the current track into this screen's action bar.
- The controller broadcasts its messages to every screen on the stack, so this screen's bar updates while it is on top and stays current for the `MainScreen` below it.

`action_channel` says "Already on this channel." and the "channel" menu entry is hidden. `s` on a tab without a sort says so ("Playlists have no sort order."); choosing "Most viewed" says "Loading from yt-dlp (slower)…" because that sort bypasses InnerTube.

## Workers and counters

| Group | Worker | Guard |
|---|---|---|
| `ch_info` | `_load_channel_info` | none; latest wins (`exclusive`) |
| `ch_thumb` | `_avatar_worker` (info-column avatar) | `_info_avatar_session` |
| `ch_content` | `_load_content` (first page of a tab) | `_content_session` |
| `ch_extend` | `_extend_content` (continuation pages) | `_content_session` |
| `focus`, `stream_prefetch`, `thumb` | from `DetailFocusMixin` (right-hand detail panel) | `_focus_session`, `_thumb_session` |

Groups are per node, so this screen's `ch_thumb` does not interact with `MainScreen`'s group of the same name.

`_info_avatar_session` is separate from the counters `DetailFocusMixin` bumps on every cursor move. The info-column avatar does not depend on the highlighted row; if it shared the cursor-bumped counter, moving the cursor while it loads would drop the avatar and leave "Loading…" forever. `_content_session` is bumped on tab, sort and reload so a slow earlier load cannot overwrite a newer list. Workers never touch the list: they hand a page to `_show_first_page` / `_apply_extension` through `_call_ui` (`App.call_ui`, dropped when the screen was popped or the app quit), and those check the session on the UI thread.

## Global keys

`/`, `,`, `?` and `q` are bound (`keymap.SEARCH`, `keymap.GLOBAL`). Help, settings and the queue page open over this page. Search belongs to the main screen (search results land in its list), so `_on_main_screen(method)` pops this screen and calls the method on the screen beneath.

## Content loading

- Tab switch, sort and reload call `_start_content_load`. `_start_content_once` (50 ms after mount) and the first `TabActivated` race to start the first load; `_content_started` makes whichever comes second a no-op.
- The channel id comes from `channel_ref.channel_id` on the URL, then from the loaded info, then from one `innertube.resolve_channel_id` lookup on the worker (cached in `_resolved_id`; an `/@handle` URL has no id until then).
- Videos sorted by date, Shorts and Live use `innertube.fetch_channel_page`. An empty first page of Videos falls back to yt-dlp (`ytdlp.fetch_channel_videos`); Shorts and Live have no fallback ("No content found."). Other sorts always use yt-dlp and return one batch with no continuation. Entries from InnerTube get the channel name filled in (`_label`).
- Playlists use `innertube.fetch_channel_playlists` (up to 80, one shot) under the same rule (id known, else or on empty, `ytdlp.fetch_channel_playlists`).
- **Prefetch.** `ChannelPager` (`src/channel_pager.py`) holds the continuation token. `_maybe_prefetch` runs after the first page, after every page change and after every applied extension; it fetches when the user is on the second-to-last held page and never while a filter is active. Paging past the last page while a fetch runs sets `_pending_show` so the batch is shown the moment it lands. The footer note ("loading 30 more…", "first 200 shown") goes through `VideoListPanel.set_progress`. Pages are appended with `VideoListPanel.append_pages`, as Home does, so the page after a 30-entry batch is partly filled (20 + 10 rows).
- Avatar ids are `ch_<channel_id>` (`_avatar_id`), distinct from video ids, so `ThumbnailWidget`'s stale-id guard also covers channel switches.

## Tabs

All four tabs are composed; `_show_tabs` hides the ones the channel lacks. Until the info arrives only Videos and Playlists show. `fetch_channel_info` returns the `tabs` the channel has; `_apply_info` shows exactly those (when `videos` is among them). The yt-dlp info fallback has no `tabs`, so the default two stay. `_cycle_tab` and the backtick picker (`ChannelTabModal`) use the shown tabs only. If the open tab disappears the page falls back to Videos.

`f` filters the loaded videos or playlists (`ListNavMixin.action_filter`); `Esc` clears a kept filter before it leaves the page. Marks, `D` and `u` are not bound here.

`i` (`keymap.CHANNEL_PAGE`) expands or collapses the description in the info column. The handoff named `a` or Enter; `a` plays audio and Enter opens the action menu on this page, so neither can mean "expand".

## Playlists inside the page

`ChannelPlaylistMixin` (`docs/code/src/tui/screens/mixins/channel_playlist.py.md`) opens a playlist row in place and adds `P` / `E` / `S`. `_content_kind()` is `playlist` while one is open, and the breadcrumb gets its name as the last crumb.

## Breadcrumb and back stack

`ChannelScreen(url, name, trail)` takes the crumbs of where it was opened from (`MainScreen._crumbs()` gives the tab label; a `ChannelScreen` gives its own trail plus its channel name). `_show_breadcrumb` writes `Home › Name › Videos  ← esc to go back` into the list panel's breadcrumb line after every content start and when the info arrives (the info's channel name wins over the name from the row). The back stack is the screen stack: `c` on a row that names a different channel (`_is_other_channel`: a `channel_id` or `channel_url` id that differs from `_known_id()`) pushes another `ChannelScreen` with the extended trail, and `Esc` pops back to the first. A row with no channel id, which is what InnerTube's channel rows carry, counts as this channel: the menu entry stays hidden and `c` says "Already on this channel.". `_known_id` never does a lookup, so it is safe on the UI thread; `_channel_id` (workers only) adds the one `resolve_channel_id` call.

## Following

`B` (`keymap.CHANNEL_PAGE`) follows or unfollows this channel locally through `channel_bookmarks.toggle`, storing the name and the avatar URL from the loaded info. It needs the `UC…` id without a lookup (`_known_id`): from a handle URL it says "The channel is still loading." until the info arrives.

## Playlist page

`ChannelScreen(url, name, trail, playlist=row)` is the playlist's own page (`_solo`; opened by `ItemActionsMixin._open_playlist` from a Search or Home row). It is the same three columns: `_apply_playlist_info` turns the header that rides on the first page (`ChannelPage.info`, `channel_info_panel.playlist_panel_info`) into the left column, the list is the playlist's videos, and `Screen.-playlist` hides the tab strip. Not loaded: channel info (`_load_channel_info` is skipped; a playlist without a header, or the yt-dlp fallback, shows the row's own title) and the tab handlers (`on_tabs_tab_activated` returns at once, so the hidden strip cannot reset `_playlist`). `s`, `B`, `H`/`L` and the backtick menu answer through `_no_tabs`; `o` (`action_owner`) opens the owner channel from the header's channel id, and `c` opens the channel of the highlighted video (`_is_other_channel` is true for any row with a channel here, because the page has no channel of its own). `Esc` leaves in one press (`_leave_playlist` returns False when `_solo`). An alert with no header (private, deleted, or a Mix that needs an account) shows YouTube's sentence in the list and skips the yt-dlp fallback. The breadcrumb is `trail › Playlist: <title>`. `_tool_actions` drops follow and adds play all, enqueue all and save. The footer note is `first 200 of N shown` when the header's count is over the cap (`ChannelPager.start(..., total)`).
