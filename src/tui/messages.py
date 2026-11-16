"""Textual messages shared between screens and mixins."""

from __future__ import annotations

from textual.message import Message


class PlayerStateUpdated(Message):
    """Audio playback state, posted to the active screen after each mpv poll.

    ``playing=False`` signals that playback stopped; ``pos`` and ``dur`` are then 0.
    """

    def __init__(self, pos: float, dur: float, paused: bool, *, playing: bool) -> None:
        super().__init__()
        self.pos = pos
        self.dur = dur
        self.paused = paused
        self.playing = playing
