# src/tui/audio_queue.py

The upcoming and played tracks of `AudioController`: enqueue, play-many, skip, back, and the queue page's move/remove/insert/clear/play.

- A track is never both playing and queued (`_start` filters it out); the queue page tells rows apart by id.
- Every edit that changes the queue broadcasts `AudioQueueChanged`; a no-op broadcasts nothing.
- `_remember` records the outgoing track for `<` only when the id changes.
