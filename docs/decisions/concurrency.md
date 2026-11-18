# Concurrency

Worker model, worker topology, cancellation, and process lifetime.

## 2026-04-25 — `@work(thread=True, exclusive=True)` for network calls

Textual's event loop is async but single-threaded for DOM updates. yt-dlp calls are synchronous and can block for seconds. `@work(thread=True)` runs them in threads and keeps the UI responsive. `exclusive=True` cancels any in-flight worker of the same type before starting a new one, which prevents races when users navigate quickly.

## 2026-05-03 — HomeScreen v2 worker topology

The original screen fanned out 3–5 concurrent subprocesses on home open:
- 1 × `yt-dlp stream_flat` (initial feed)
- 2 × `yt-dlp fetch_full` from a `ThreadPoolExecutor(max_workers=2)`, triggered eagerly by `BatchRevealed(20 ids)`
- 1 × silent `yt-dlp` background revalidate
- 1 × `chafa --optimize=3 --color-space=din99d` per cursor keystroke, with no kill of the previous one

It also ran `set_interval(600, _scheduled_home_refresh)` and `set_interval(0.5, _poll_audio_ipc)`.

The redesign collapses this to three screen-owned, exclusive workers:
- `feed_loader`: runs only on cold start, explicit `R`, or a stale-cache tab dwell.
- `focus`: fires after a 200 ms cursor dwell. It runs `fetch_full` for the focused video and, best effort, one neighbour in the cursor's last direction.
- `thumb`: fires after a 150 ms cursor dwell. It checks the RAM and disk chafa caches before spawning a chafa subprocess.

Each worker stores its `Popen` handle on the screen and `terminate()`s the previous one before dispatching a new request. `@work(exclusive=True)` only swaps the Python wrapper, so this backs it with an OS-level cancellation. Session counters guard against late callbacks racing with cancellation.

The 10-minute `_scheduled_home_refresh` `set_interval` is deleted. It fired whichever tab the user was on, which matched reports of "the spike happened while I wasn't even on home". Freshness now shows in the list-panel header (`updated 4m ago · R to refresh`), refreshed every 60 s by a single `Static.update`.

Housekeeping moved out of `App.on_mount` into a 60-second `set_timer` plus an `on_unmount` backstop, so it no longer competes with the home feed render at startup.

Chafa flags and the render cache from the same redesign are in [thumbnails](thumbnails.md). The cache-hit refresh change is in [feeds-and-paging](feeds-and-paging.md).

## 2026-06-17 — Unified process registry and structured shutdown

The exit system was redesigned to eliminate orphaned child processes on every exit path.

Problem: three overlapping cleanup mechanisms (`on_unmount`, `atexit`, `_emergency_cleanup`) each covered a different subset of processes. The 600 ms `os._exit(0)` bypassed `atexit` entirely. mpv video processes had no backstop in any exit handler.

Solution: a singleton `ProcessRegistry` in `src/plat.py` that all subprocess-spawning code registers into:
- yt-dlp processes: through the `_register_proc`/`_unregister_proc` wrappers.
- mpv audio: registered on Popen, unregistered in `_stop_audio`.
- mpv video: registered in `WatchModal._launch_video`, unregistered in `finally`/`action_stop`.
- `ProcessRegistry.kill_all(timeout)` sends SIGTERM, waits, then SIGKILL for stragglers.

Exit paths, in layers:
1. `action_quit_app`: `_stop_audio()` + `app.exit()` + a 2 s failsafe timer.
2. The 2 s failsafe calls `ProcessRegistry.kill_all()` before `os._exit(0)`.
3. `on_unmount`: `ProcessRegistry.kill_all()` + `ytdlp.kill_all_active()`.
4. `atexit`: same as `on_unmount`.
5. SIGTERM/SIGHUP: the signal handler calls `ProcessRegistry.kill_all()` + `sys.exit()`.

Startup `reap_orphans()` handles the SIGKILL case, where no cleanup is possible. It cleans stale `/tmp/termtube-mpv*.sock` files and kills orphaned mpv processes found via `pgrep`.

## 2026-11-18 — A failed store write never raises into the UI
Playlist create/add and other synchronous `JsonStore.update` calls re-raised `OSError`; no caller caught it, so a read-only or full disk
crashed the app with a traceback. Now every failed write logs, keeps the change in memory, stays dirty (retried by the next write and at
exit), and tells the user once per failing streak through `store.set_failure_hook` (the app's `_store_save_failed`, thread-aware). Single-writer
assumption: there is no cross-process lock; a second TermTube running at once can overwrite the first's file (last writer wins).
