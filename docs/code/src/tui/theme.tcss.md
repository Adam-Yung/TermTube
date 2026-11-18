# src/tui/theme.tcss

The app stylesheet (`App.CSS_PATH`). Crimson is the base; amber, ocean and midnight are overrides under `App.theme-<name>`, toggled by `SettingsModal`.

- Every themed selector appears once per theme with only the accent, header and highlight colours changed. A new themed widget needs a rule in all three blocks.
- Every modal is centered by the one `ModalScreen { align: center middle; }` rule. Every dialog box carries `class="dialog"` (`height: auto`, at most 90% of the screen each way, `min-width: 36`, scrolls when it must); a list inside it carries `dialog-list` (`max-height: 50vh`, so the title and hint always stay in the box). A new modal sets those two classes and only its width and colours by id. Layout rules: `docs/decisions/ui.md` (2026-11-18).
- Titles, hints and list items share rules by comma-grouped selectors. Add a new modal id to the groups rather than a new block.
- Rich markup colours (in `video_list.py`, `action_bar.py`, `help_screen.py`, `download_picker_modal.py`) cannot read this file; they check the app class instead.
- `ThumbnailWidget`, `PageIndicator` and `ActionBar` carry their own `DEFAULT_CSS`; the help screen is styled here only. `#thumbnail-area` is `height: 25` capped at half the detail panel, so the info and the Actions panel keep room on a short terminal.
- Notifications: `ToastRack` and `Toast` (Textual's own widgets, no ids in Python) are styled at the end of the file; `Toast.-information` takes the theme accent per theme, `-warning` and `-error` are fixed. Decision: `docs/decisions/ui.md`. `run_test` hides toasts unless called with `notifications=True`.
- Textual component classes (`.bar--bar`, `.footer-key--key`, `.scrollbar--thumb`) never appear in Python; they are not dead.
- Every id and class here must appear in `src/**/*.py`; remove a rule with the widget that owned it.

`QueueModal` (`Q`) uses `#queue-dialog`, `#queue-title`, `#queue-hint` and `#queue-list`; `#queue-title` is in the per-theme accent lists with the other dialog titles. `NameModal` and `YtdlpUpdateModal` take their ids from the playlist and image-warning groups.
