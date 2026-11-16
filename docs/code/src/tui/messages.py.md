# src/tui/messages.py

Textual `Message` classes shared across screens and mixins. Messages that belong to one widget stay in that widget's file.

`PlayerStateUpdated` carries one mpv poll result to the UI: `pos`, `dur`, `paused`, and `playing`. `playing=False` means playback stopped
and `pos`/`dur` are 0. `AudioController` broadcasts it with `screen.post_message(...)` to every screen on the stack (`App.post_message` does not reach screens, `AGENTS.md`); a modal on top receives its own copy and ignores it.

`AudioTrackChanged(entry, queue_len)`, `AudioQueueChanged(queue_len)` and `AudioSegmentsLoaded(segments)` carry the other changes the action bar shows. All four are handled by `AudioBarMixin`.
