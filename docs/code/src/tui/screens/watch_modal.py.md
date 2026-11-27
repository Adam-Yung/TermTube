# src/tui/screens/watch_modal.py

`WatchModal` plays one video in an external mpv window and mirrors progress in the TUI. It owns the video mpv process and its IPC socket (`plat.get_video_ipc_path()`), separate from the audio player's socket. Pushed by `mixins/item_actions.py`. History: `docs/decisions/playback.md`.

## Flow

- `on_mount` starts the `video_player` worker (`_launch_video`) and a 0.5 s timer that polls mpv (`mpv_poll` worker group).
- URL resolution goes through `streams.resolve_for_playback` (cache, in-flight prefetch, fresh resolve plus CDN probe). Local files (`_local_path`) skip it and mpv opens the path.
- A local file is played directly (`urls = [local_path]`, so `--no-ytdl -- <path>`); the ytdl options are only for page URLs.
- If no stream URL resolves, mpv gets the page URL with `--ytdl-format` and the cookie options and resolves it itself.
- Launching and retrying is `player.run_mpv_with_retries` (3 attempts); the modal supplies the command builder. From the second attempt, `streams.re_resolve` drops the cached URL (it may have expired) and the command is rebuilt. History is added when the first attempt spawns.
- `_finish` dismisses with a result string: `ended` (exit 0), `next` / `prev` (exit 10 / 11 from the mpv window of a run), `failed`, else `stopped`; `stale` (the user stopped or stepped) dismisses nothing, `_end` already did.
- The poll timer never dismisses: it cannot know the exit code, and setting `_stopped` from it made the launcher read a finished mpv as stale.
- SponsorBlock segments load on a daemon thread alongside resolution; the launcher waits at most 2 s for them. `_set_segments` resets the pointer and the progress-bar column cache.

## Invariants

- `_stopped` is set before anything is torn down. The launcher checks it after resolution and before each attempt, and `_end` uses it to avoid dismissing twice.
- The auto-skip pointer (`_sb_next_idx`) only moves forward; segments are sorted by start.
- The IPC socket and temp input.conf are cleaned up on every exit path (`_cleanup_ipc`).
- Dismissing from the worker thread goes through `call_from_thread`; the screen may already be gone, so failures are swallowed.

## Markup

The title and channel are escaped with `fmt.escape_markup`; the key hint writes the `[ ]` seek keys as `\\[ ]`.

## Playlist runs

`position=(n, total)` marks one item of a run (`mixins/playlist_rows.py` chains them). It shows in the header, adds the run keys to mpv's input.conf, and gives the item its own IPC socket: stepping starts the next modal while the old worker is still removing its socket. `<` / `>` end the modal directly rather than through mpv, so they also work while the URL resolves.

## Keys

h/l/left/right and `[` `]` seek 5 s, H/L and `{` `}` seek 10 s, 0-9 seek to 0-90 %, space pauses, q/Esc stops, `<` / `>` step through a run. Defined in `BINDINGS` here, not in `keymap.py`; the on-screen hint (`#np-hint`) and `docs/features/keybindings.md` must change with them.

## Limits

The progress bar needs mpv's IPC to answer; until it does the modal shows "Buffering...".

## Resume and watch time

`_launch_video` asks `progress.start_offset` for the saved position and passes it to `_build_command`, which adds `--start` through `player.start_args`; a "Resuming at m:ss" notice follows. A `ProgressTracker` is created next to `history.add` (first spawn) and fed from `_poll_mpv_threaded`; it is finished when `run_mpv_with_retries` returns, whatever the outcome, with `completed` only for exit code 0 (end of file). Rules: `docs/code/src/progress.py.md`.
