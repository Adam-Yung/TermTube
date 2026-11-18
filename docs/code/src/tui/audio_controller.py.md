# src/tui/audio_controller.py

Background audio: a headless mpv controlled over an IPC socket, with a queue, SponsorBlock auto-skip and progress reporting. One `AudioController` lives on the app (`app.audio`, created in `TermTubeApp.__init__`), so music survives every screen push and pop. Screens call its public methods (`play_audio`, `enqueue_audio`, `play_many` (play the first, queue the rest, replacing the queue), `enqueue_many` (queue what is not playing or queued, one notice), `skip_audio`, `stop_audio`, `toggle_audio_pause`, `seek_audio`, `seek_audio_percent`, `can_enqueue`) through `ItemActionsMixin` and mirror its state through messages (`docs/code/src/tui/screens/mixins/audio_bar.py.md`). Decisions: `docs/decisions/playback.md`.

## Session and stale rules

`_session` increases on every `_start`. Every worker, timer callback and completion handler receives the number it started under and drops its work when `session != self._session` or `_stopped` is set (`_stale`). This is the only cancellation mechanism: the mpv thread and the URL resolution cannot be interrupted, so late results are discarded instead.

- `_play_pending` is true from `_start` until mpv is spawned (1-3 s of URL resolution). `is_playing` includes it, so a second press during that window cannot start a second player. `_clear_pending(session)` clears it on every exit path, but only for the current session so a stale worker cannot clear the flag of the new track.
- The IPC socket path is a function of the session number (`_socket_for(session)`), and each worker uses the session it holds, never the current one. A dying mpv from the previous track cannot answer polls for the next one, and a stale worker cannot address the new socket.
- `play_audio` stops the old track first (`_stop` reads the old session's socket, so the `quit` command and socket cleanup hit the right mpv) and `_start` bumps the counter afterwards. Both run in one UI-thread call, so no worker sees a state in between.
- Completion (`_on_finished`, `_on_failed`) and `_launch_failed`'s stop run on the UI thread through `call_from_thread` and re-check the session, so a late failure of an old track never stops the new one.

## Threads and messages

`_launch_worker` is a thin wrapper that logs (with traceback) and reports any exception from the launch body (`_launch`) through `_launch_failed`; a raw thread would swallow it and the bar would stay on "Buffering…".

Threads are plain daemon threads (the controller is not a DOM node, so no `@work`): `audio-launch` (one per start) and `audio-poll` (one per 0.5 s timer tick, skipped while the previous poll is still waiting on mpv, which is what `exclusive` used to do). The timer is `app.set_interval`.

State changes reach screens as messages broadcast to every screen on `app.screen_stack` (`_broadcast` builds a fresh message per screen), not only the active one. A covered screen therefore stays current and a modal on top cannot swallow an update. `PlayerStateUpdated` (progress, and `playing=False` on stop, finish or failure), `AudioTrackChanged`, `AudioQueueChanged`, `AudioSegmentsLoaded`: `src/tui/messages.py`. A replaced track posts `AudioTrackChanged` only; no stop message is sent between the two tracks.

`log` is a hook (`MainScreen` sets it to its debug-log writer in `on_mount`); the default discards.

## Launch and retry loop

Launch and retry run through `player.run_mpv_with_retries` (`docs/code/src/player.py.md`).

1. Suppress the video from the home feed, start the SponsorBlock fetch in the background.
2. A local file (`_local_path`) is passed to mpv as a direct file (`stream_url = local`: `--no-ytdl -- <path>`), never as a page URL with ytdl options. Otherwise resolve the stream URL via `streams.resolve_for_playback` (cache, then yt-dlp, then CDN warm-up; no cookies, public CDN URLs). Local files (`_local_path`) skip this and play directly.
3. `_play_with_retries`: up to 3 attempts, 1 s apart. Attempts after the first re-resolve the URL (`streams.re_resolve`), because the usual cause is an expired or rejected CDN URL. mpv's stderr is captured.
4. Outcome `ok` (exit 0 or 4) means finished; `killed` (3) means stopped by us, no message; `failed` calls `_on_failed`, which shows the first stderr line via `player.friendly_mpv_error` and moves to the next queued track; `stale` only clears the pending flag.

A missing or GUI-only mpv (mpv.net on Windows) is a launch failure, not a retry.

## Progress polling

`poll_once(session)` reads position, duration and pause state over IPC. Results are ignored when pos or dur is None (mpv not ready, socket gone) or the session moved on. `_publish_progress` then:

- adds the entry to history on the **first successful poll of a session** (`_history_session`). A track enters history only when mpv actually produced a position, so failed launches, cancelled starts and stale-URL retries never leave a history row;
- stores `progress`, which a screen created mid-playback reads in `_sync_player_bar` so its bar does not restart at "Buffering";
- broadcasts `PlayerStateUpdated`.

SponsorBlock auto-skip runs in the poll thread: `_segment_idx` walks the sorted segments and a seek command jumps past the segment containing the current position.

## Stop

`_stop` sets `_stopped`, sends `quit`, terminates the process, unregisters it from `ProcessRegistry`, resets state, broadcasts `PlayerStateUpdated(playing=False)` (unless `keep_player_mode`, used when a new track follows) and removes the socket.

## Sharp edges

- The queue is in memory only.
- `app.screen_stack` is read from whichever thread calls `_broadcast`; all callers are on the UI thread (completions, `_publish_progress`, `apply`).

## Queue edits and progress

`move_queued`, `remove_queued`, `insert_queued` (undo) and `play_queued` are the only queue edits besides enqueue/skip/stop; each broadcasts `AudioQueueChanged` through `_queue_changed`. Indexes are positions in the *upcoming* queue; the playing track is never in it, so it cannot be removed (the queue modal says `>` or `x`). `play_queued(i)` plays that track now and keeps the ones before it, like `a` keeps the queue. `insert_queued` ignores an entry that is playing or queued, so undo cannot create a duplicate.

A `ProgressTracker` is created on the first poll of a session, next to `history.add`, and fed from `_publish_progress`. It is finished in `_reset_playback` (every stop, switch and failure) and with `completed=True` from `_on_finished`, which clears the resume point. `_play_with_retries` asks `progress.start_offset` once and puts `--start` in every attempt's command, with a "Resuming at m:ss" notice. See `docs/code/src/progress.py.md`.
