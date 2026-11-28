# src/tui/widgets/segment_bar.py

The progress bar of both players: played cells in the player's colour, SponsorBlock cells in green (dim when not yet reached). The column map is cached by (width, duration) because it is recomputed twice a second otherwise; `set_segments` drops it. The zero-duration look differs per player, so each handles it before calling `render`.
