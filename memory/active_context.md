# Active Context

## Current Task: COMPLETED
Cookie system rewrite + feed speed optimization.

## What Was Done
- Eliminated cookies.txt entirely — yt-dlp now uses `cookiesfrombrowser` on every call
- Browser auto-detection via `src.browsers`; user can set `browser: none` to disable
- Removed: cookies_ready Event, _auto_refresh_cookies, CookieWarningModal, cookie_args()
- Added `browser_cookie_args()` on Config for mpv passthrough
- Removed os.fsync() from cache atomic writes (was adding 30-60ms × N entries)
- Single-fetch architecture: one yt-dlp call for 80 entries with progressive callback at 15
- Changed home feed URL from /feed/recommended to https://www.youtube.com/ (proven faster)

## Key Technical Notes
- `_play_pending` flag still guards audio race condition (from prior work)
- `on_first_batch` callback in `fetch_page_batch` fires at first_batch_size entries
- `cookiesfrombrowser` tuple format: `(browser_name, None, None, None)`
- If browser extraction fails, yt-dlp continues unauthenticated (no crash)
- `approximate_date` + `source_address: '0.0.0.0'` + `playlistend` for speed
