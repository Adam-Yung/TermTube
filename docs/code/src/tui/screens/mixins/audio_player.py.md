# src/tui/screens/mixins/audio_player.py

Background audio: a headless mpv controlled over an IPC socket, with a queue, SponsorBlock auto-skip and progress reporting. `MainScreen` owns it; `ChannelScreen` reaches it through `_audio_host()` (`docs/code/src/tui/screens/mixins/item_actions.py.md`). Decisions: `docs/decisions/playback.md`.

## Session and stale rules

`_audio_session` increases on every `_start_audio` (and when `play_audio` replaces a running track). Every worker, timer callback and completion handler receives the number it started under and drops its work when `session != self._audio_session` or `_audio_stopped` is set (`_stale`). This is the only cancellation mechanism: the mpv thread and the URL resolution cannot be interrupted, so late results are discarded instead.

- `_play_pending` is true from `_start_audio` until mpv is spawned (1-3 s of URL resolution). `is_audio_playing` includes it, so a second press during that window cannot start a second player. `_clear_pending(session)` clears it on every exit path, but only for the current session so a stale worker cannot clear the flag of the new track.
- The IPC socket path includes the session number (`_audio_socket`), so a dying mpv from the previous track cannot answer polls for the next one.
- Completion (`_on_audio_finished`, `_on_audio_failed`) runs on the UI thread through `call_from_thread` and re-checks the session.

## Launch and retry loop

Worker group `audio_player` (`thread=True`, not exclusive: staleness is handled by the session):

1. Suppress the video from the home feed, start the SponsorBlock fetch in the background.
2. Resolve the stream URL via `streams.resolve_for_playback` (cache, then yt-dlp, then CDN warm-up; no cookies, public CDN URLs). Local files (`_local_path`) skip this and play directly.
3. `_play_with_retries`: up to 3 attempts, 1 s apart. Attempts after the first re-resolve the URL (`streams.re_resolve`), because the usual cause is an expired or rejected CDN URL. mpv's stderr is captured.
4. Exit code 0 (end of file) or 4 (quit command) means finished; 3 (killed by signal) means stopped by us, no message; anything else retries, and after the last attempt `_on_audio_failed` shows the first stderr line via `player.friendly_mpv_error` and moves to the next queued track.

A missing or GUI-only mpv (mpv.net on Windows) is a launch failure, not a retry.

## Progress polling

A 0.5 s timer starts a worker in group `audio_poll` (`thread=True, exclusive=True`) that reads position, duration and pause state over IPC. Results are ignored when pos or dur is None (mpv not ready, socket gone). `_publish_progress` then:

- adds the entry to history on the **first successful poll of a session** (`_history_session`). A track enters history only when mpv actually produced a position, so failed launches, cancelled starts and stale-URL retries never leave a history row;
- updates this screen's `ActionBar`;
- posts `PlayerStateUpdated` to `self.app.screen`, the active screen. `self.app.post_message` does not reach screens. `ChannelScreen.on_player_state_updated` mirrors the state into its own bar; `MainScreen` has no handler because it updates its bar directly.

SponsorBlock auto-skip runs in the poll worker: `_segment_idx` walks the sorted segments and a seek command jumps past the segment containing the current position.

## Stop

`_stop_audio` sets `_audio_stopped`, sends `quit`, terminates the process, unregisters it from `ProcessRegistry`, restores the action bar (unless `keep_player_mode` for a track change), posts `PlayerStateUpdated(playing=False)` and removes the socket.

## Sharp edges

- `play_audio` bumps `_audio_session` before calling `_stop_audio`, and `_audio_socket()` derives the path from the session, so `_stop_audio` addresses the next session's socket, not the one the old mpv listens on. `terminate_process` still kills the old process; only the `quit` command and socket cleanup miss.
- The queue is in memory only.
