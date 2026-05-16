# Active Context

Status: COMPLETED May 2026
Task: Cookie architecture refactor + settings reformat + updater cookie refresh

## What was done
1. **Cookie architecture simplified** — removed `auth_required` parameter from
   `Config.cookie_args()`, `ytdlp.cookie_args()`, `stream_flat()`,
   `fetch_page_batch()`, and all call sites. Browser fallback (`--cookies-from-browser`)
   is never used at runtime; only `--cookies <path>` when cookies.txt exists.

2. **Cookie refresher added** — `updater.refresh_cookies()` extracts cookies
   from the configured browser via yt-dlp, writes to `.tmp` then atomically
   renames. Wired into `run_all_updates()` (weekly cadence). New CLI flag
   `--refresh-cookies` for manual extraction.

3. **Settings page reformatted** — removed ugly Authentication section;
   cookie status (path + freshness age) folded into Cookie Browser section
   as a subtitle. Matches the head+ListView rhythm of other sections.

4. **mpv.net winget upgrade removed** — `_update_commands()` no longer tries
   `winget upgrade --id mpv.net` (mpv is now bundled via setup.ps1).

## Tests
- 235 unit tests pass (5 new for refresh_cookies).

## Pending
- Step 7 of HomeScreen v2 (observe_property event reader in player.py)
  remains deferred to a separate PR per existing memory.
