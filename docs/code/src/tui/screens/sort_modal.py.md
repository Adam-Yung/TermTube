# src/tui/screens/sort_modal.py

Sort picker for channel videos. Dismisses `"date"` or `"views"`, or `None`. Styled in `theme.tcss` with `NavModal`'s selectors (`#sort-dialog`, `#sort-title`, `#sort-hint`, rows use the shared `.nav-row` class), so it follows the colour themes. The key numbers in the rows take `THEME_COLORS` for the active theme at compose time.
