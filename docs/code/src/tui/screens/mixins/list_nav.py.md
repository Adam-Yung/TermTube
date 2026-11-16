# src/tui/screens/mixins/list_nav.py

Cursor, page and focus handling for a screen that owns one `VideoListPanel` (`MainScreen`, `ChannelScreen`). The screen sets `_LIST_ID`. Bindings come from `keymap.LIST_NAV` (`docs/features/keybindings.md`).

## Interface

- `action_page_next` is a no-op while the panel is loading, loads the next page when it is held, and otherwise calls `_on_past_last_page()`. After landing on the last held page it calls `_on_last_page_reached()`. `FeedLoaderMixin` implements both hooks to extend the feed (prefetch in the background on the last page, blocking with a spinner when the user presses past it). `ChannelScreen` leaves them empty.
- `action_goto_end` loads the last held page with the cursor on its last row.
- `on_video_list_panel_page_change_requested` routes clicks on the `PageIndicator` to the same actions as `h`/`l`.

## Focus reclaim

`on_key` returns focus to the list for the keys in `keymap.FOCUS_RECLAIM_KEYS`. Appending list items can move focus onto the tab bar; without this, `j`/`k` would stop moving the cursor.
