# src/tui/audio_controller.py

Background audio: a headless mpv controlled over an IPC socket, with a queue, SponsorBlock auto-skip and progress reporting. One `AudioController` lives on the app (`app.audio`, created in `TermTubeApp.__init__`), so music survives every screen push and pop. Screens call its public methods (`play_audio`, `enqueue_audio`, `skip_audio`, `stop_audio`, `toggle_audio_pause`, `seek_audio`, `seek_audio_percent`, `can_enqueue`) through `ItemActionsMixin` and mirror its state through messages (`docs/code/src/tui/screens/mixins/audio_bar.py.md`). Decisions: `docs/decisions/playback.md`.

## Session and stale rules

`_session` increases on every `_start`. Every worker, timer callback and completion handler receives the number it started under and drops its work when `session != self._session` or `_stopped` is set (`_stale`). This is the only cancellation mechanism: the mpv thread and the URL resolution cannot be interrupted, so late results are discarded instead.

- `_play_pending` is true from `_start` until mpv is spawned (1-3 s of URL resolution). `is_playing` includes it, so a second press during that window cannot start a second player. `_clear_pending(session)` clears it on every exit path, but only for the current session so a stale worker cannot clear the flag of the new track.
- The IPC socket path is a function of the session number (`_socket_for(session)`), and each worker uses the session it holds, never the current one. A dying mpv from the previous track cannot answer polls for the next one, and a stale worker cannot address the new socket.
- `play_audio` stops the old track first (`_stop` reads the old session's socket, so the `quit` command and socket cleanup hit the right mpv) and `_start` bumps the counter afterwards. Both run in one UI-thread call, so no worker sees a state in between.
- Completion (`_on_finished`, `_on_failed`) and `_launch_failed`'s stop run on the UI thread through `call_from_thread` and re-check the session, so a late failure of an old track never stops the new one.

## Threads and messages

Threads are plain daemon threads (the controller is not a DOM node, so no `@work`): `audio-launch` (one per start) and `audio-poll` (one per 0.5 s timer tick, skipped while the previous poll is still waiting on mpv, which is what `exclusive` used to do). The timer is `app.set_interval`.

State changes reach screens as messages broadcast to every screen on `app.screen_stack` (`_broadcast` builds a fresh message per screen), not only the active one. A covered screen therefore stays current and a modal on top cannot swallow an update. `PlayerStateUpdated` (progress, and `playing=False` on stop, finish or failure), `AudioTrackChanged`, `AudioQueueChanged`, `AudioSegmentsLoaded`: `src/tui/messages.py`. A replaced track posts `AudioTrackChanged` only; no stop message is sent between the two tracks.

`log` is a hook (`MainScreen` sets it to its debug-log writer in `on_mount`); the default discards.

## Launch and retry loop

1. Suppress the video from the home feed, start the SponsorBlock fetch in the background.
2. Resolve the stream URL via `streams.resolve_for_playback` (cache, then yt-dlp, then CDN warm-up; no cookies, public CDN URLs). Local files (`_local_path`) skip this and play directly.
3. `_play_with_retries`: up to 3 attempts, 1 s apart. Attempts after the first re-resolve the URL (`streams.re_resolve`), because the usual cause is an expired or rejected CDN URL. mpv's stderr is captured.
4. Exit code 0 (end of file) or 4 (quit command) means finished; 3 (killed by signal) means stopped by us, no message; anything else retries, and after the last attempt `_on_failed` shows the first stderr line via `player.friendly_mpv_error` and moves to the next queued track.

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
