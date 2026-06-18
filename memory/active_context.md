# Active Context

## Status: COMPLETED — Jun 17 2026

## Session: Codebase audit — stability, UX, and performance hardening

### Summary of Changes

**Phase 1a — Exit Logic Hardening:**
1. Added `ProcessRegistry` singleton in `src/platform.py` — unified tracker for all child processes (mpv, yt-dlp, chafa)
2. Registered SIGTERM/SIGHUP signal handlers in `src/main.py` for cleanup on terminal close
3. Replaced 600ms `os._exit(0)` bomb with 2s structured shutdown (kill all procs, then force exit)
4. Added startup orphan reaper (`reap_orphans()`) that cleans stale sockets and kills leftover mpv processes
5. Integrated ProcessRegistry into yt-dlp, mpv audio, mpv video, and download modal
6. Download cancel now terminates the subprocess immediately
7. Fixed `--update` falling through to TUI launch (missing `sys.exit`)

**Phase 1b — Critical Stability:**
1. Atomic writes for `history.json` and `playlists.json` (tmpfile + `os.replace`)
2. Retry logic (1 retry, 2s delay) for `fetch_page_batch` and `fetch_search_batch`
3. Replaced `_housekeeping_done` bool with `threading.Event` (eliminates race condition)
4. Kill process on `TimeoutExpired` in `fetch_channel_info` (prevents zombie yt-dlp)

**Phase 2 — UX Quick Wins:**
1. Buffering indicator with elapsed time for audio ("Buffering… (Xs)")
2. Same buffering indicator for video playback in WatchModal
3. Friendly mpv error translation table (HTTP 403 → cookies expired, etc.)
4. `Config.save()` now logs a warning on failure instead of silent swallow

**Phase 3 — Performance:**
1. Cache pruning uses `stat().st_mtime` instead of reading+parsing every JSON file
2. Thumbnail re-render on resize debounced to 300ms (prevents chafa subprocess storms)
