# src/tui/screens/channel_tab_modal.py

Backtick tab picker on the channel screen. Dismisses a tab id (`ch-tab-videos`, `ch-tab-playlists`) or `None`. Styled in `theme.tcss` with `NavModal`'s selectors (`#ch-tab-dialog`, `#ch-tab-title`, `#ch-tab-hint`, rows use `.nav-row`), so it follows the colour themes. The key numbers in the rows take `THEME_COLORS` for the active theme at compose time.
