"""Resume point and watch time: turns mpv's polled position into the history fields `resume_s` and `seconds`."""

from __future__ import annotations

import threading

from src import history
from src.entries import Entry

MIN_RESUME_S = 10
DONE_FRACTION = 0.95
SAVE_EVERY_S = 5.0
MAX_POLL_STEP_S = 3.0


def is_live(entry: Entry) -> bool:
    return bool(entry.get("is_live") or entry.get("live_status") == "is_live")


def resume_point(pos: float, dur: float) -> int | None:
    """Where to resume after stopping at ``pos`` of ``dur``; None when too early or as good as finished."""
    if dur <= 0 or pos < MIN_RESUME_S or pos >= dur * DONE_FRACTION:
        return None
    return int(pos)


def start_offset(entry: Entry, config) -> int | None:
    """Seconds to start ``entry`` at: its saved resume point; None when resuming is off, it is live or stale."""
    vid = entry.get("id")
    if not vid or is_live(entry) or not config.resume_playback_enabled:
        return None
    record = history.get(vid) or {}
    saved = record.get("resume_s")
    if isinstance(saved, bool) or not isinstance(saved, int | float) or saved < MIN_RESUME_S:
        return None
    dur = record.get("duration") or entry.get("duration") or 0
    return int(saved) if not dur or saved < dur * DONE_FRACTION else None


class ProgressTracker:
    """Feeds one playback's polled positions into the history record.

    Watch time grows by the step between polls, ignoring seeks and pauses (a step must be positive and at most
    ``MAX_POLL_STEP_S``). The record is written every ``SAVE_EVERY_S`` seconds of watched time, not of wall time,
    and once more on `finish`. Polls may come from a worker thread, so every call takes one lock.
    """

    def __init__(self, entry: Entry) -> None:
        self._vid = entry.get("id")
        self._live = is_live(entry)
        self._lock = threading.Lock()
        self._last: float | None = None
        self._pos = 0.0
        self._dur = 0.0
        self._unsaved = 0.0
        self._done = self._live or not self._vid

    def tick(self, pos: float, dur: float) -> None:
        with self._lock:
            if self._done or dur <= 0:
                return
            if self._last is not None and 0 < pos - self._last <= MAX_POLL_STEP_S:
                self._unsaved += pos - self._last
            self._last = self._pos = pos
            self._dur = dur
            if self._unsaved >= SAVE_EVERY_S:
                self._write(completed=False)

    def finish(self, *, completed: bool = False) -> None:
        """Write the final position (None when ``completed``); later calls do nothing."""
        with self._lock:
            if not self._done and self._dur > 0:
                self._write(completed=completed)
            self._done = True

    def _write(self, *, completed: bool) -> None:
        resume = None if completed else resume_point(self._pos, self._dur)
        history.record_progress(self._vid, resume_s=resume, watched=self._unsaved, duration=self._dur)
        self._unsaved = 0.0
