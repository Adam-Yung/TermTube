# Active Context

## Completed tasks (2026-04-25)

### Setup/config cleanup
1. Fixed `--sync` symlink: `rm -rf APP_DIR && ln -s ORIG_DIR APP_DIR` — `.venv` lives in repo.
2. Removed conda/mamba from `setup.sh`, `termtube`, `uninstall.sh`. venv only.
3. Added `--help` to `setup.sh`.
4. Config moved to `~/.config/TermTube/config.yaml`. Default created on first run.
5. Updated README, CLAUDE.md, created `memory/`.

### Audio queue + copy URL features
1. **Config auto-creation** — `config.py` calls `self.save()` when config doesn't exist.

2. **Copy video URL (`y`)** — `action_copy_url` + `_copy_video_url(entry)` in `main_screen.py`. Tries `pbcopy` → `xclip` → `wl-copy`, falls back to notification. Also in `VideoActionModal` as "⎘ Copy video URL (y)".

3. **Audio queue (`e` + `>`)** — `_audio_queue: list[dict]` on `MainScreen`.
   - `e`: queue focused video (only when audio playing and focused != playing)
   - `>`: skip to next queued track
   - Natural end of track auto-plays from queue
   - Explicit `s` stop clears the queue
   - Queue length shown in ActionBar player mode via `#np-queue-line` / `update_queue_hint()`
   - `ActionBar._HEIGHT_PLAYER` raised from 10 → 11 for the new queue line widget

## Completed tasks (2026-05-03)

### Logging system overhaul
1. **`src/logger.py` rewritten**:
   - Without `--debug`: level set to `CRITICAL+1`, no handlers attached → all `logger.*` calls are zero-cost no-ops.
   - With `--debug`: writes to `$TMPDIR/TermTube/<TIMESTAMP>.log`, mirrors to stderr, and forwards to a registered TUI sink.
   - New API: `register_tui_sink(cb)`, `unregister_tui_sink()`, `file_only(msg, *args)`, `log_file()`.
   - `_TUIHandler` honours a `_termtube_skip_tui` record attribute (used by `file_only`).

2. **`MainScreen` (`src/tui/screens/main_screen.py`)**:
   - On mount, registers `_on_log_record` as the TUI sink. Sink marshals to UI thread via `app.call_from_thread(_write_log_to_widget, …)`.
   - `_write_log_to_widget` writes a coloured level glyph + message to the `#debug-log` RichLog.
   - `_log()` is now a no-op when `--debug` off; otherwise writes markup to RichLog and mirrors plain text via `logger.file_only` (so no duplicate write).
   - `action_toggle_log` shows a yellow hint pointing to `--debug` when debug is off.
   - Added `logger.info/debug` calls for: tab activation, refresh, cursor top/bottom, search submit/cancel, watch, dl_video, dl_audio, quit.

3. **Coverage added**:
   - `tui/app.py`: mount/theme, housekeeping prune.
   - `cache.py`: put_video, put_feed, register_focus (suppress crossing), suppress_video, clear_feed, clear_all, prune_old_thumbnails, prune_old_videos.
   - `ytdlp.py`: download_video_with_progress, download_audio_with_progress, kill_all_active. (yt-dlp commands & cache hit/miss were already logged.)
   - `player.py`: send_ipc_command (gated on `is_debug()` to avoid building dict reprs when off).
   - `tui/widgets/video_list.py`: lazy batch reveals.
   - `main.py`: startup banner, dependency check, config load, clear cache.

## Completed tasks (2026-05-03 — follow-ups)

### Logging follow-ups & silent-mpv fix
1. **`src/logger.py`**: stderr handler removed entirely — it was corrupting Textual's rendering. Only the file handler (`$TMPDIR/TermTube/<ts>.log`) and the TUI sink remain when `--debug` is on. `setup()` now takes a `level` arg.
2. **`src/main.py`**: new `--level {ALL,DEBUG,INFO,WARNING,ERROR,CRITICAL}` flag (default `ALL`, alias for DEBUG). `--debug` help text updated to drop the stderr mention. `logger.setup(debug=…, level=…)` wired through.
3. **`src/tui/screens/main_screen.py` `_launch_audio_worker`**:
   - `--really-quiet`/`--msg-level=all=no` replaced with `--msg-level=all=error` so failures actually surface.
   - mpv is now spawned with `stderr=subprocess.PIPE` and drained via `communicate()` (avoids pipe-buffer deadlock).
   - Returncode is inspected: `0`/`4` ⇒ success (history + finished toast), `3` ⇒ user-stopped (silent), anything else ⇒ failure path.
   - New `_on_audio_failed(entry, returncode, stderr)` method: does NOT add to history, logs the warning, and shows an error notification with mpv's first stderr line. Auto-skips to next queued track if any.
4. **README.md**: new "Debugging" section documenting `--debug` and `--level`.

## Completed tasks (2026-05-03 — HomeScreen v2)

Goal: tame the ~30 % CPU spike on home open by shrinking the worker topology
from 3–5 concurrent subprocesses + two `set_interval`s to three screen-owned,
exclusive, OS-cancellable workers + one app-level idle housekeeper. Plan lives
in `memory/HomeScreenv2.md` (status: implemented, smoke test pending).

### What landed
1. **Eager batch enrichment removed.** `enrich_in_background` and the
   `ThreadPoolExecutor` deleted from `src/ytdlp.py`.
   `MainScreen.on_video_list_panel_batch_revealed` no longer fans out
   `fetch_full` calls. Replaced with a 200 ms cursor-dwell `_focus_worker` that
   runs **one** `fetch_full` for the focused video plus (best-effort) one
   neighbour in the cursor's last direction.
2. **Chafa cache + cheaper flags.** `src/ui/thumbnail.py` now flags
   `--optimize=1` (was `--optimize=3 --color-space=din99d`). Output is cached
   on disk under `~/.cache/termtube/chafa/<vid>_<cols>x<rows>_<fmt>.ansi` and in
   a 64-entry `OrderedDict` LRU on `MainScreen` keyed by `(vid, cols, rows)`.
3. **Subprocess cancellation.** Both `_focus_worker` and `_thumb_worker` store
   the spawned `Popen` on `self`; the next dispatch `terminate()`s the previous
   one before launching anew. `ytdlp.fetch_full` and `thumbnail.render` accept
   an `on_proc_started` callback for this purpose. Session counters guard
   against late callbacks racing with cancellation.
4. **10-min `set_interval` removed.** `_scheduled_home_refresh` and
   `_background_refresh_worker` deleted. Refresh now happens only on cold
   start, on the `R` keybind, or after a 5 s dwell on a feed tab whose cache is
   older than 60 min (handled in the tab-activation handler).
5. **Stale-while-revalidate path removed.** Cache hits no longer kick a silent
   parallel `yt-dlp` to revalidate.
6. **O(1) `update_entry_by_id`.** `VideoListPanel` keeps an `_items_by_id`
   dict; `update_entry_by_id` is now a single dict lookup.  Added
   `neighbor_id`, `cursor_index`, `set_freshness`, `_render_header` helpers.
   The list-panel header shows `{n} videos · updated {age} · R to refresh`,
   refreshed every 60 s.
7. **DetailPanel is passive.** All worker dispatch removed from the panel; the
   screen pushes content via `update_basic`, `set_description`,
   `set_thumbnail_loading`, `set_thumbnail_image`, `set_thumbnail_ansi`,
   `set_thumbnail_placeholder`, `refresh_metadata`. Resize/`ScreenResume` post
   a `RerenderRequested` message that the screen handles by re-kicking the
   thumb worker.
8. **Audio poll gating (interim).** `_audio_poll_timer` is started/stopped on
   the audio bar's display transitions; no more unconditional 0.5 s tick.
   The `observe_property` event-reader rewrite of `src/player.py` is **deferred
   to a separate PR** — not blocking HomeScreen v2.
9. **Housekeeping moved off mount.** `tui/app.py` schedules
   `prune_old_thumbnails` / `prune_old_videos` / `prune_old_chafa` 60 s after
   mount via `set_timer`; `on_unmount` is a backstop.

### Files touched
- `src/cache.py` — added `feed_age(key)`.
- `src/ytdlp.py` — removed `enrich_in_background`; added `on_proc_started` to `fetch_full`.
- `src/ui/thumbnail.py` — disk + RAM chafa cache; cheaper flags; `prune_old_chafa`.
- `src/tui/widgets/video_list.py` — `_items_by_id`, `neighbor_id`, `cursor_index`, freshness header.
- `src/tui/widgets/detail_panel.py` — passive view; `RerenderRequested` message.
- `src/tui/screens/main_screen.py` — new `_focus_worker` / `_thumb_worker` / `_kick_*` / `_cancel_pending_focus_and_thumb`; cursor-dwell debounce timers; LRU chafa RAM cache; tab-activation stale-check; freshness label tick; removed `_scheduled_home_refresh`, `_background_refresh_worker`, `_make_enrich_callback`, eager batch enrichment.
- `src/tui/app.py` — housekeeping moved to 60 s `set_timer` + `on_unmount` backstop.
- `memory/architecture_decisions.md` — added "HomeScreen v2 worker topology (May 2026)" section.

### Pending (out of scope for landing, but tracked)
- Human smoke test of acceptance criteria in `memory/HomeScreenv2.md` §7.
- Step 7 final: rewrite `src/player.py` to use mpv `observe_property` instead of any polling.
- Optional: README mention of the `updated Nm ago · R to refresh` footer.
