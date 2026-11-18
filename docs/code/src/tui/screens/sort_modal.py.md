# src/tui/screens/sort_modal.py

Sort picker for channel videos. Dismisses `"date"` or `"views"`, or `None`. Styled in `theme.tcss` with `NavModal`'s selectors (`#sort-dialog`, `#sort-title`, `#sort-hint`, rows use the shared `.nav-row` class), so it follows the colour themes. The key numbers in the rows take `THEME_COLORS` for the active theme at compose time.

It is the one picker for every sort or type choice. `options` is a list of `(key, label, letter)` rows (default `CHANNEL_SORTS`: date `d`, views `v`), `title` the heading; row N is picked with the digit N or its letter (`on_key`), the current key gets a tick. The channel page passes nothing; the Search tab passes its sort rows (`s`) and type rows (`t`).
