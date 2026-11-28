# src/tui/screens/mixins/channel_content.py

Loads and pages the channel page's list. `channel_screen.py.md` describes the page and its sources.

- `ch_content` loads the first page, `ch_extend` the next ones. `_content_session` drops results from before a tab, sort or reload.
- `_channel_id` may block (one lookup) and is for workers only; `_known_id` is safe on the UI thread.
- InnerTube first, yt-dlp as fallback for newest videos and playlists. InnerTube rows carry no channel name, so `_label` fills it.
- `_maybe_prefetch` fetches ahead on the second-to-last held page, never while filtering.
