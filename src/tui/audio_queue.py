"""What plays next and what played before: the queue operations of the audio controller."""

from __future__ import annotations

from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup
from src.tui.messages import AudioQueueChanged


class AudioQueueMixin:
    """The upcoming and played tracks of ``AudioController``.

    Needs ``_queue``, ``_played``, ``_entry``, ``_app``, ``is_playing``, ``claim``, ``play_audio``, ``_start``,
    ``_stop`` and ``_broadcast`` from the controller.
    """

    @property
    def queue(self) -> tuple[Entry, ...]:
        return tuple(self._queue)

    @property
    def has_previous(self) -> bool:
        return self.is_playing and bool(self._played)

    def can_enqueue(self, entry: Entry) -> bool:
        """True while audio plays and ``entry`` is neither the current track nor already queued."""
        return self.is_playing and not self._is_current(entry) and not self._is_queued(entry)

    def _is_current(self, entry: Entry) -> bool:
        return entry.get("id") == (self._entry or {}).get("id")

    def _is_queued(self, entry: Entry) -> bool:
        return any(e.get("id") == entry.get("id") for e in self._queue)

    def enqueue_audio(self, entry: Entry) -> None:
        if not self.is_playing:
            self.play_audio(entry)
            return
        entry_id = entry.get("id")
        if entry_id and self._is_current(entry):
            self._app.notify(text("audio_controller.already_playing"), timeout=2)
        elif entry_id and self._is_queued(entry):
            self._app.notify(text("audio_controller.already_queued"), timeout=2)
        else:
            self._queue.append(entry)
            title = entry.get("title", text("audio_controller.default_title"))
            self._app.notify(text("audio_controller.added_to_queue", title=escape_markup(title[:40])), timeout=3)
            self._queue_changed()

    def play_many(self, entries: list[Entry]) -> None:
        """Play the first entry now and queue the rest, replacing the queue (a playlist's play-all)."""
        if not entries:
            return
        self._queue = list(entries[1:])
        self.play_audio(entries[0])
        self._played.clear()
        self._queue_changed()

    def enqueue_many(self, entries: list[Entry]) -> int:
        """Queue each entry not playing or queued, with one notice (idle: start the first). Returns the count."""
        fresh, seen = [], {(self._entry or {}).get("id"), *(e.get("id") for e in self._queue)}
        for entry in entries:
            if entry.get("id") not in seen:
                seen.add(entry.get("id"))
                fresh.append(entry)
        if not fresh:
            return 0
        if not self.is_playing:
            self.play_many(fresh)
        else:
            self._queue.extend(fresh)
            self._queue_changed()
        key = "audio_controller.queued_one" if len(fresh) == 1 else "audio_controller.queued_many"
        self._app.notify(text(key, count=len(fresh)), timeout=3)
        return len(fresh)

    def skip_audio(self) -> None:
        if not self.is_playing or not self._queue:
            return
        self.play_audio(self._queue.pop(0))

    def previous_audio(self) -> None:
        """Go back to the track played before this one; this one returns to the head of the queue."""
        if not self.has_previous:
            return
        self.claim()
        self._queue.insert(0, self._entry)
        entry = self._played.pop()
        self._stop(keep_player_mode=True)
        self._start(entry)
        self._queue_changed()

    def _remember(self, outgoing: Entry | None, incoming: Entry) -> None:
        if outgoing and outgoing.get("id") != incoming.get("id"):
            self._played.append(outgoing)

    def _advance_queue(self, outgoing: Entry) -> bool:
        if not self._queue:
            self._played.clear()
            return False
        self._remember(outgoing, self._queue[0])
        self._start(self._queue.pop(0))
        return True

    def move_queued(self, index: int, step: int) -> int:
        """Move the upcoming track at ``index`` by ``step`` places (clamped to the queue). Returns its new index."""
        if not 0 <= index < len(self._queue):
            return index
        new = min(len(self._queue) - 1, max(0, index + step))
        if new != index:
            self._queue.insert(new, self._queue.pop(index))
            self._queue_changed()
        return new

    def remove_queued(self, index: int) -> Entry | None:
        """Drop the upcoming track at ``index`` and return it (None when out of range); the playing one is not queued"""
        if not 0 <= index < len(self._queue):
            return None
        entry = self._queue.pop(index)
        self._queue_changed()
        return entry

    def insert_queued(self, index: int, entry: Entry) -> None:
        """Put ``entry`` back at ``index`` (undo of a removal), unless it is playing or queued again meanwhile."""
        if self._is_current(entry) or self._is_queued(entry):
            return
        self._queue.insert(min(max(index, 0), len(self._queue)), entry)
        self._queue_changed()

    def clear_queue(self) -> list[Entry]:
        """Drop every upcoming track and return them in order; the playing one goes on."""
        cleared = list(self._queue)
        if cleared:
            self._queue.clear()
            self._queue_changed()
        return cleared

    def play_queued(self, index: int) -> None:
        """Play the upcoming track at ``index`` now. The tracks before it stay queued, in order (nothing is dropped)."""
        if not 0 <= index < len(self._queue):
            return
        entry = self._queue.pop(index)
        self.play_audio(entry)
        self._queue_changed()

    def _queue_changed(self) -> None:
        self._broadcast(lambda: AudioQueueChanged(len(self._queue)))
