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

## No active in-progress work.
