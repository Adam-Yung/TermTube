# src/tui/theme.tcss

The app stylesheet (`App.CSS_PATH`). Crimson is the base; amber, ocean and midnight are overrides under `App.theme-<name>`, toggled by `SettingsModal`.

- Every themed selector appears once per theme with only the accent, header and highlight colours changed. A new themed widget needs a rule in all three blocks.
- Modals share rules by comma-grouped selectors (dialog box, title, hint, list items). Add a new modal id to the groups rather than a new block.
- Rich markup colours (in `video_list.py`, `action_bar.py`, `help_screen.py`, `download_picker_modal.py`) cannot read this file; they check the app class instead.
- `ThumbnailWidget`, `PageIndicator`, `ActionBar` and `HelpScreen` carry their own `DEFAULT_CSS` and are not styled here (help and action-bar ids still appear here for theme overrides).
- Notifications: `ToastRack` and `Toast` (Textual's own widgets, no ids in Python) are styled at the end of the file; `Toast.-information` takes the theme accent per theme, `-warning` and `-error` are fixed. Decision: `docs/decisions/ui.md`. `run_test` hides toasts unless called with `notifications=True`.
- Textual component classes (`.bar--bar`, `.footer-key--key`, `.scrollbar--thumb`) never appear in Python; they are not dead.
- Every id and class here must appear in `src/**/*.py`; remove a rule with the widget that owned it.
