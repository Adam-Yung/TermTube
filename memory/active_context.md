# Active Context

## Current Task: COMPLETED
Fix playback race condition, cookies staleness, and home feed speed.

## What Was Done
- Added `_play_pending` flag to prevent audio race condition when play is pressed before URL resolves
- Auto-refresh cookies.txt from browser on app startup (non-blocking, before first feed fetch)
- Respect `browser: none` config to disable all cookie operations
- Added yt-dlp optimizations: IPv4 forcing, geo_bypass, approximate_date, playlistend
- Two-phase feed fetch: 15 entries fast (~2-3s), then background fill to 80
- Ensured stash saves on all exit paths (on_unmount backstop for Ctrl+C / SIGHUP)

## Key Technical Notes
- `_play_pending` is set immediately in `_start_audio` and checked in `_audio_playing` property
- Cookie auto-refresh uses a `threading.Event` (`cookies_ready`) to coordinate with feed fetch
- Feed fetch waits max 10s for cookies, but stash is displayed before the wait
- `approximate_date` extractor arg avoids exact upload date resolution (big speedup)
- `source_address: '0.0.0.0'` forces IPv4 (avoids IPv6 timeout fallback on some networks)
