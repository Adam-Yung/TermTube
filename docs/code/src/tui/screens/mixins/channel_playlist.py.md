# src/tui/screens/mixins/channel_playlist.py

Lets `ChannelScreen` open one of the channel's playlists in place and act on all of it. `Enter` on a playlist row sets `_playlist` and restarts the content load; `_content_kind()` then returns `"playlist"`, so the first page comes from `_fetch_playlist_videos` and later pages from `innertube.fetch_playlist_page` under the same `ChannelPager` as the tabs (prefetch, cap 200, session guard). `Esc` and Backspace first close a kept filter, then `_leave_playlist` (back to the Playlists list), then pop the screen. Switching tabs drops `_playlist`.

## Bulk keys (`P` play all, `E` enqueue all, `S` save)

- Only inside a playlist; elsewhere they say "Open a playlist first".
- They use what is loaded when the pager has no token left. If more pages exist, `_gather_playlist` (group `ch_gather`) walks the continuations to the cap and the result goes through `call_from_thread` to `_run_bulk`, which drops it when `_content_session` has moved on. A gather that fails part way enqueues or saves nothing and shows the typed message as a hint. While a page is loading they refuse with a hint.
- `P` calls `AudioController.play_all` (replaces the queue, plays the first); `E` calls `enqueue_many` (skips the playing track and anything queued; starts playback when idle). Rows that are not videos are dropped.
- `S` stores each row in the cache (`cache.put_video`, so the local playlist shows titles offline) and appends the ids to the local playlist named like the channel playlist through `playlist.add_videos`. It adds only ids not yet in it, so pressing `S` twice changes nothing.

## Fallback and limits

The first page falls back to yt-dlp (`fetch_page_batch` on the playlist URL, no continuation) when InnerTube returns nothing. `innertube.fetch_playlist_page` reads `playlistVideoListRenderer`; **[verify live]**: the shape and fixture `innertube_playlist_videos.json` are hand-written. Rows of other channels' videos carry `channel_id`, so `c` on them opens that channel with this one in the breadcrumb.
