# src/tui/segment_skip.py

SponsorBlock auto-skip state for one track. `take(pos)` returns each segment once; the pointer only moves forward, so seeking back does not skip again. Replacing the object is how new segments or a new track reset it.
