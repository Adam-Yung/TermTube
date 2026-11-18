# src/tui/screens/queue_modal.py

`Q`: the audio queue as a modal. The playing track is the first row (marked `▶`), the upcoming tracks follow, numbered. The modal holds no queue state: every edit calls `app.audio` (`move_queued`, `remove_queued`, `insert_queued`, `play_queued`) and then redraws from `app.audio.queue`. That keeps the controller the single owner (`docs/code/src/tui/audio_controller.py.md`).

- **Live.** It redraws on `AudioQueueChanged`, `AudioTrackChanged` and a `PlayerStateUpdated(playing=False)`, which the controller broadcasts to every screen on the stack, so the list stays right when a track ends behind it. The cursor stays on the same video when it can, otherwise on the same row.
- **Playing track.** It cannot be moved or removed; `D` says so (`>` skips, `x` stops) and `Enter` says it is already playing.
- **Undo.** `D` pushes `(index, entry)` on a modal-local stack; `u` re-inserts at that index through `insert_queued`, which refuses an entry that is playing or queued again. The stack dies with the modal.
- `Enter` plays the highlighted upcoming track now and leaves the tracks before it queued, in order. This matches `a` (play now, keep the queue). It does not drop or rotate anything.
- Opened from `ItemActionsMixin.action_audio_queue`, so every screen that binds `keymap.PLAYBACK` has it. With nothing playing and nothing queued it is a hint, not an empty dialog.
