"""Textual messages shared between screens and mixins."""

from __future__ import annotations

from textual.message import Message


class PlayerStateUpdated(Message):
    """Audio playback state, broadcast to every screen after each mpv poll.

    ``playing=False`` signals that playback stopped; ``pos`` and ``dur`` are then 0.
    """

    def __init__(self, pos: float, dur: float, paused: bool, *, playing: bool) -> None:
        super().__init__()
        self.pos = pos
        self.dur = dur
        self.paused = paused
        self.playing = playing


class AudioTrackChanged(Message):
    """A track started (or replaced the previous one); the action bar switches to player mode."""

    def __init__(self, entry: dict, queue_len: int) -> None:
        super().__init__()
        self.entry = entry
        self.queue_len = queue_len


class AudioQueueChanged(Message):
    """The queue gained a track; the enqueue hint needs a refresh."""

    def __init__(self, queue_len: int) -> None:
        super().__init__()
        self.queue_len = queue_len


class AudioSegmentsLoaded(Message):
    """SponsorBlock segments for the current track arrived."""

    def __init__(self, segments: list) -> None:
        super().__init__()
        self.segments = segments
