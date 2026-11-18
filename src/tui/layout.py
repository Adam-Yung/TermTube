"""Size rules shared by the screens and their stylesheet (``docs/decisions/ui.md``, 2026-11-18)."""

NARROW_BELOW = 100
"""Narrower terminals get ``-narrow`` on every screen: shorter tabs, a collapsed rail, no channel info column."""
HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (NARROW_BELOW, "-wide")]
MIN_INFO_ROWS = 6
"""The detail panel's video info (title, channel, stats, some description) keeps these rows before anything else."""
MIN_THUMB_ROWS = 6
"""A thumbnail shorter than this is not worth drawing; the panel hides it and gives the rows to the info."""
MAX_THUMB_ROWS = 25
