# src/tui/screens/empty_feed_modal.py

Shown when a feed returns no videos, which usually means browser auth is not working (`docs/decisions/cookies-and-auth.md`). Dismisses `"update"` (run the yt-dlp updater), `"settings"` or `"skip"`; Esc is skip. The caller decides what each result does.
