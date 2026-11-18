# src/tui/layout.py

The size rules that code and `theme.tcss` share, so no number lives in two places. `NARROW_BELOW` (100 columns) feeds `App.HORIZONTAL_BREAKPOINTS`: every screen gets `-narrow` below it and `-wide` from it, and the stylesheet keys on those classes (tabs, channel info column). `LibraryRailMixin` collapses the rail at the same width. `MIN_INFO_ROWS`, `MIN_THUMB_ROWS` and `MAX_THUMB_ROWS` are the vertical budget of the detail panel (`DetailPanel.fit`, `ActionBar`). Rules and reasons: `docs/decisions/ui.md` (2026-11-18, part B).
