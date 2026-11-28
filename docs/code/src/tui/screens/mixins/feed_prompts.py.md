# src/tui/screens/mixins/feed_prompts.py

The dialogs `MainScreen` raises around feeds and startup. `_show_empty_feed_modal` and `_prompt_ytdlp_update` are called from loader threads through `_ui`. The yt-dlp update runs in a plain (non-exclusive) thread worker. `_refresh_account` invalidates the cookie jar so the next load re-reads the browser.
