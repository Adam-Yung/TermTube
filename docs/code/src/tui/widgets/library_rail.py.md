# src/tui/widgets/library_rail.py

`LibraryRail`: a focusable widget that renders its own rows (no child widgets, so replacing the entries is synchronous). The cursor only
highlights; `Enter` or a click posts `Chosen(view)`. `current` is the collection the list shows (bold, accent colour). `narrow` renders one line,
`◂ label  count ▸ i/n`, for terminals narrower than `layout.NARROW_BELOW`; the same keys cycle entries. When there are more entries than
rows the window follows the cursor. The widget knows nothing about playlists or the Library: the screen supplies `RailItem`s and reacts to `Chosen`.
