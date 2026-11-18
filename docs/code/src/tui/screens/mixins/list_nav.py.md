# src/tui/screens/mixins/list_nav.py

Cursor, page and focus handling for a screen that owns one `VideoListPanel` (`MainScreen`, `ChannelScreen`). The screen sets `_LIST_ID`. Bindings come from `keymap.LIST_NAV` (`docs/features/keybindings.md`).

## Interface

- `action_page_next` is a no-op while the panel is loading, loads the next page when it is held, and otherwise calls `_on_past_last_page()`. After landing on a page (and after `action_goto_end`) it calls `_on_page_shown()`. The hooks have no default here on purpose: `ListNavMixin` precedes `FeedLoaderMixin` in `MainScreen`'s MRO, so a no-op default would shadow the loader (which is how Home never extended in the real app before P7.3). `FeedLoaderMixin` implements `_on_page_shown` and `_on_past_last_page`; `ChannelScreen` has its own.
- `action_goto_end` loads the last held page with the cursor on its last row.
- `on_video_list_panel_page_change_requested` routes clicks on the `PageIndicator` to the same actions as `h`/`l`.

## Filter

`action_filter` opens the panel's filter bar (`f`). `_close_filter_if_active` is what Esc/Backspace call first on both screens: a kept filter is cleared before the key goes back. `ChannelScreen` gets the filter and nothing else of the list tools.

## Focus reclaim

`on_key` returns focus to the list for the keys in `keymap.FOCUS_RECLAIM_KEYS`, except while the filter bar has focus (otherwise `Enter` in the bar would also activate the row, and arrow keys would leave the field). Appending list items can move focus onto the tab bar; without this, `j`/`k` would stop moving the cursor.

A focused widget with `OWNS_NAV_KEYS = True` (the Library rail) is exempt from the focus reclaim, like the filter bar.
