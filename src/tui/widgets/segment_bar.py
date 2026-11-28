"""The played/remaining progress bar with SponsorBlock segments in green, shared by both players."""

from __future__ import annotations

from itertools import groupby
from operator import itemgetter

from src.sponsorblock import Segment

EMPTY_COLOR = "#2a2a40"
_SPONSOR_COLOR = "#22c55e"
_SPONSOR_DIM = "#166534"


class SegmentBar:
    """Caches which columns fall inside a segment until the segments, width or duration change."""

    def __init__(self) -> None:
        self._segments: list[Segment] = []
        self._cols: list[bool] = []
        self._cols_for: tuple[int, float] = (0, 0.0)

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self._cols = []

    def render(self, pos: float, dur: float, width: int, color: str) -> str:
        """Rich markup of ``width`` cells; ``dur`` must be positive."""
        filled = int(min(pos / dur, 1.0) * width)
        if not self._segments:
            return f"[{color}]{'█' * filled}[/{color}][{EMPTY_COLOR}]{'░' * (width - filled)}[/{EMPTY_COLOR}]"
        cells = [
            ((_SPONSOR_COLOR if inside else color), "█")
            if col < filled
            else ((_SPONSOR_DIM if inside else EMPTY_COLOR), "░")
            for col, inside in enumerate(self._columns(width, dur))
        ]
        return "".join(
            f"[{tone}]{''.join(char for _, char in run)}[/{tone}]" for tone, run in groupby(cells, key=itemgetter(0))
        )

    def _columns(self, width: int, dur: float) -> list[bool]:
        if self._cols_for != (width, dur) or len(self._cols) != width:
            self._cols = [
                any(s.start <= (col / width) * dur < s.end for s in self._segments) for col in range(width)
            ]
            self._cols_for = (width, dur)
        return self._cols
