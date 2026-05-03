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

## No active in-progress work.
