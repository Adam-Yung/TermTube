# Active Context

## Current Task: COMPLETED
Performance and stability audit — implemented 4 priority fixes.

## What Was Done
1. **Moved `_prefetch_next_page_meta` out of `feed_loader` worker** — it now schedules a `_focus_worker` call via `call_from_thread(self._schedule_prefetch)` so the feed_loader thread exits cleanly after fetching pages. Enforces the strict "one thread for pages, one thread for video info" model.
2. **Added process cleanup on exit** — `on_unmount` now calls `ytdlp.kill_all_active()` before housekeeping, and an `atexit` handler provides last-resort cleanup if `on_unmount` doesn't fire.
3. **Added 30s read timeout to yt-dlp streaming** — uses `select.select()` + `os.read()` instead of blocking `for line in proc.stdout`. If no data arrives within 30s, the subprocess is killed and the worker unblocks.
4. **Registered download subprocess in `_active_procs`** — `_run_download_with_progress` now adds/removes its proc to the global registry so `kill_all_active()` terminates downloads on quit.

## Key Design Decisions in This Session
- `_schedule_prefetch` runs on the main thread (via `call_from_thread`) and dispatches to the existing `_focus_worker` — this reuses the session counter + exclusive group for correct cancellation.
- The read timeout uses `os.read(fd, 65536)` directly (not `proc.stdout.read()`) to guarantee non-blocking behavior after `select` returns.
- `atexit` handler is a static method to avoid preventing GC of the App instance.
