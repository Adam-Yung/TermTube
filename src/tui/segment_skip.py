"""SponsorBlock auto-skip for a playing track, shared by the audio and video players."""

from __future__ import annotations

from src.sponsorblock import Segment


class SegmentSkipper:
    """Segments sorted by start, each offered once as playback reaches it; the pointer only moves forward."""

    def __init__(self, segments: list[Segment] | None = None) -> None:
        self.segments: list[Segment] = [] if segments is None else segments
        self._next = 0

    def take(self, pos: float) -> Segment | None:
        """The segment containing ``pos`` that has not been skipped yet, or None."""
        segments = self.segments
        while self._next < len(segments) and segments[self._next].end <= pos:
            self._next += 1
        if self._next >= len(segments):
            return None
        segment = segments[self._next]
        if not segment.start <= pos < segment.end:
            return None
        self._next += 1
        return segment
