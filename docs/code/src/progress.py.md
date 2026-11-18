# src/progress.py

Turns mpv's polled position into the history fields `resume_s` (where to resume) and `seconds` (time actually watched). Both players use it: `AudioController` holds one `ProgressTracker` per track, `WatchModal` one per window.

## Rules

- **Resume point.** `resume_point(pos, dur)`: none below 10 s (`MIN_RESUME_S`) and none from 95 % (`DONE_FRACTION`) of the length. A track that ends on its own (`completed`) clears it.
- **Reading it.** `start_offset(entry, config)` returns the saved point only when `resume_playback` is on, the entry is not live (`is_live`, `live_status == "is_live"`), the record has a point of at least 10 s and the point is still under 95 % of the length. Otherwise None, and mpv starts at 0. The offset reaches mpv through `player.start_args`, the only place the `--start=<s>` flag is built.
- **Watch time.** `tick(pos, dur)` adds the step since the previous poll only when it is positive and at most 3 s (`MAX_POLL_STEP_S`). A pause adds nothing; a seek forward or back, a SponsorBlock skip or a replay adds nothing. Polls come every 0.5 s, so a real step is about 0.5 s.
- **Debounce.** A write happens once 5 s (`SAVE_EVERY_S`) of watched time has built up, not every poll, and once in `finish()`. Each write is a deferred store update (`history.record_progress`), so the UI thread never waits on the disk; `history.flush()` on quit writes the rest.
- **Live and id-less entries** record nothing.
- A tracker is created when the history row is created (first poll for audio, first spawn for video), so a failed launch writes no progress.
- `finish()` is idempotent, and a tracker that never saw a poll writes nothing. Calls take one lock: audio polls arrive on the UI thread, video polls on a worker, `finish` from the mpv wait thread.

## Known limits

- Stopping mpv by killing the app between two debounced writes loses up to 5 s of watched time and moves the resume point back by at most that much.
