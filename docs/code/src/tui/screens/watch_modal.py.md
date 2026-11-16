# src/tui/screens/watch_modal.py

`WatchModal` plays one video in an external mpv window and mirrors progress in the TUI. It owns the video mpv process and its IPC socket (`plat.get_video_ipc_path()`), separate from the audio player's socket. Pushed by `mixins/item_actions.py`. History: `docs/decisions/playback.md`.

## Flow

- `on_mount` starts the `video_player` worker (`_launch_video`) and a 0.5 s timer that polls mpv (`mpv_poll` worker group).
- URL resolution goes through `streams.resolve_for_playback` (cache, in-flight prefetch, fresh resolve plus CDN probe). Local files (`_local_path`) skip it and mpv opens the path.
- If no stream URL resolves, mpv gets the page URL with `--ytdl-format` and the cookie options and resolves it itself.
- Up to 3 launches. From the second, `streams.re_resolve` drops the cached URL (it may have expired) and the command is rebuilt.
- Exit codes 0, 3 and 4 are normal exits (3 is the kill from the stop key); anything else retries.
- SponsorBlock segments load on a daemon thread alongside resolution; the launcher waits at most 2 s for them. `_set_segments` resets the pointer and the progress-bar column cache.

## Invariants

- `_stopped` is set before anything is torn down. The launcher checks it after resolution and before each attempt, and `_poll_mpv` uses it to avoid dismissing twice.
- The auto-skip pointer (`_sb_next_idx`) only moves forward; segments are sorted by start.
- The IPC socket and temp input.conf are cleaned up on every exit path (`_cleanup_ipc`).
- Dismissing from the worker thread goes through `call_from_thread`; the screen may already be gone, so failures are swallowed.

## Keys

h/l/left/right and `[` `]` seek 5 s, H/L and `{` `}` seek 10 s, 0-9 seek to 0-90 %, space pauses, q/Esc stops. Defined in `BINDINGS` here, not in `keymap.py`; the on-screen hint (`#np-hint`) and `docs/features/keybindings.md` must change with them.

## Limits

The progress bar needs mpv's IPC to answer; until it does the modal shows "Buffering...".
