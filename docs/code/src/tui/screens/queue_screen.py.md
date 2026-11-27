# src/tui/screens/queue_screen.py

`q`: the audio queue as a page. `VideoListPanel` and `DetailPanel`, built from the same mixins as the channel page. The playing track is the first row (badged), the upcoming ones follow. The page holds no queue state: every edit calls `app.audio` (`move_queued`, `remove_queued`, `clear_queue`, `insert_queued`, `play_queued`) and redraws from `app.audio.queue` (`docs/code/src/tui/audio_controller.py.md`).

- **Live.** `_rebuild` runs on `AudioQueueChanged`, `AudioTrackChanged` and `PlayerStateUpdated(playing=False)` (`AudioBarMixin` handles the same messages for the bar; Textual calls both). It does nothing unless the playing id or the queued ids changed, so a controller broadcast after the page's own edit does not rebuild twice. The cursor stays on the same video, else on the same position.
- **Rows by id.** The list tells rows apart by video id; the controller guarantees the playing track is not also queued.
- **Playing track.** It cannot be moved or removed; `D` says so and `Enter` says it is already playing.
- **Undo.** `D` and `c` push `(index, entry)` records; `u` re-inserts them in order through `insert_queued`, which refuses an entry that is playing or queued again. The stack is dropped when audio stops and dies with the page.
- **Keys.** `keymap.QUEUE_PAGE` plus the transport part of `PLAYBACK` and the row actions without `channel` (`c` clears here). The hint line under the list is always shown, because the Actions panel gives way to the player while audio plays.
