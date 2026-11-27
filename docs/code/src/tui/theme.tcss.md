# src/tui/theme.tcss

The app stylesheet (`App.CSS_PATH`). Crimson is the base; amber, ocean and midnight are overrides under `App.theme-<name>`, toggled by `SettingsModal`.

- Every themed selector appears once per theme with only the accent, header and highlight colours changed. A new themed widget needs a rule in all three blocks.
- Every modal is centered by the one `ModalScreen { align: center middle; }` rule. Every dialog box carries `class="dialog"` (`height: auto`, at most 90% of the screen each way, `min-width: 36`, scrolls when it must); a list inside it carries `dialog-list` (`max-height: 50vh`, so the title and hint always stay in the box). A new modal sets those two classes and only its width and colours by id. Layout rules: `docs/decisions/ui.md` (2026-11-18).
- Titles, hints and list items share rules by comma-grouped selectors. Add a new modal id to the groups rather than a new block.
- Rich markup colours (in `video_list.py`, `action_bar.py`, `help_screen.py`, `download_picker_modal.py`) cannot read this file; they check the app class instead.
- `ThumbnailWidget`, `PageIndicator` and `ActionBar` carry their own `DEFAULT_CSS`; the help screen is styled here only. `#thumbnail-area` has no height cap here: `DetailPanel.fit` sets it (video info first, then the Actions panel, the thumbnail gets the rest and hides when under 6 rows).
- Columns on the main screen: the rail is `24` cells, the list `9fr` (min 40), the detail panel `11fr` (min 30), so the three never add up to more than the screen. Screens carry `-narrow` under 100 columns (`src/tui/layout.py`, set through `App.HORIZONTAL_BREAKPOINTS`): shorter tab padding so all six tabs fit 80 columns, and on the channel page the info column is hidden. `#list-breadcrumb` is one line with an ellipsis.
- Notifications: `ToastRack` and `Toast` (Textual's own widgets, no ids in Python) are styled at the end of the file; `Toast.-information` takes the theme accent per theme, `-warning` and `-error` are fixed. Decision: `docs/decisions/ui.md`. `run_test` hides toasts unless called with `notifications=True`.
- Textual component classes (`.bar--bar`, `.footer-key--key`) never appear in Python; they are not dead.
- Every id and class here must appear in `src/**/*.py`, and every type selector must name a real widget (`Scrollbar` is not one: Textual styles scrollbars through `scrollbar-color`); remove a rule with the widget that owned it. `src/tests/unit/test_theme_wiring.py` checks this.

`QueueScreen` (`q`) uses `#queue-main`, `#queue-center`, `#queue-video-list`, `#queue-hint` and `#queue-detail-panel` (`-narrow` shifts width to the detail column). `NameModal` and `YtdlpUpdateModal` take their ids from the playlist and image-warning groups.
