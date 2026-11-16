# src/tui/screens/channel_screen.py

Pushed on top of `MainScreen` for one channel: info column (`ChannelInfoPanel`), a Videos/Playlists tab bar and list in the middle, `DetailPanel` on the right. It reuses `ListNavMixin`, `DetailFocusMixin` and `ItemActionsMixin`; it has no audio of its own (`AudioBarMixin` mirrors `app.audio`).

## Audio

Audio keys act on `app.audio`, so music keeps playing across channel pages and this screen never scans the screen stack. `AudioBarMixin` shows the state:

- `on_mount` calls `_sync_player_bar` to copy the current track into this screen's action bar.
- The controller broadcasts its messages to every screen on the stack, so this screen's bar updates while it is on top and stays current for the `MainScreen` below it.

`action_channel` is a no-op and the "channel" menu entry is hidden: already on the page.

## Workers and counters

| Group | Worker | Guard |
|---|---|---|
| `ch_info` | `_load_channel_info` | none; latest wins (`exclusive`) |
| `ch_thumb` | `_avatar_worker` (info-column avatar) | `_info_avatar_session` |
| `ch_content` | `_load_content` (videos or playlists) | `_content_session` |
| `focus`, `stream_prefetch`, `thumb` | from `DetailFocusMixin` (right-hand detail panel) | `_focus_session`, `_thumb_session` |

Groups are per node, so this screen's `ch_thumb` does not interact with `MainScreen`'s group of the same name.

`_info_avatar_session` is separate from the counters `DetailFocusMixin` bumps on every cursor move. The info-column avatar does not depend on the highlighted row; if it shared the cursor-bumped counter, moving the cursor while it loads would drop the avatar and leave "Loading…" forever. `_content_session` is bumped on tab, sort and reload so a slow earlier load cannot overwrite a newer list.

## Content loading

- Tab switch, sort and reload call `_start_content_load`. `_start_content_once` (50 ms after mount) and the first `TabActivated` race to start the first load; `_content_started` makes whichever comes second a no-op.
- Videos sorted by date use `feeds.channel_latest` (RSS, then InnerTube browse; fast) when a `UC...` channel id is known (from the URL, or from the loaded info); otherwise, or if InnerTube returns nothing, yt-dlp (`ytdlp.fetch_channel_videos`) supplies them. Entries from InnerTube get the channel name filled in. Other sorts always use yt-dlp.
- Playlists use `innertube.fetch_channel_playlists` under the same rule (id known, else or on empty, `ytdlp.fetch_channel_playlists`).
- Avatar ids are `ch_<channel_id>` (`_avatar_id`), distinct from video ids, so `ThumbnailWidget`'s stale-id guard also covers channel switches.
- All results are one unpaged `add_entries(1, ...)` split into pages of 20.
