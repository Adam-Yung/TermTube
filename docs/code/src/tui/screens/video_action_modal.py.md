# src/tui/screens/video_action_modal.py

Action menu for the selected video (Enter on the list). Lists `keymap.ROW_ACTIONS` minus `hide` and dismisses the action name; the caller runs
`action_<name>` on itself. Each label is the row's text plus its bound key from `keymap.key_of`, so the menu cannot drift from the keymap or from
the Actions panel (`ActionBar` reads the same list). `ItemActionsMixin._hidden_menu_actions` removes what would only answer with a hint for the row
(a missing file, a live stream, an already downloaded item, the channel page's own channel).

`labels` (optional) overrides a row's text by action name; `ItemActionsMixin._menu_labels` uses it to relabel the enqueue entry when nothing plays.
The list sits in a `dialog` and grows to at most half the screen, then scrolls (`docs/decisions/ui.md`, 2026-11-18).
