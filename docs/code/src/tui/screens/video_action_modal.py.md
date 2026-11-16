# src/tui/screens/video_action_modal.py

Action menu for the selected video (Enter on the list). Dismisses an action key from `_ACTIONS`; the caller dispatches it. `hide` removes entries that do not apply (for example the channel page hides "Browse channel"). The `(v)`, `(a)` hints in the labels are the shortcuts from `keymap.py`; keep them in sync with `docs/features/keybindings.md`.
