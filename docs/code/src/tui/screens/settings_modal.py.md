# src/tui/screens/settings_modal.py

Edits theme, preferred quality, thumbnail format and browser. Each selection writes `config._data` and calls `Config.save()` at once; there is no Save button (`docs/decisions/config.md`).

- Theme: swaps the `theme-*` class on the app, then re-renders widgets that baked the accent colour into Rich markup (`VideoListItem`, `ActionBar`). Pure TCSS cannot reach those; see `theme.tcss.md`.
- Browser list: "auto", installed browsers from `src/browsers.py`, then supported-but-missing ones labelled "(not found)". The status line shows whether cookies will be used.
- Tab cycles the four lists; j/k move the focused list.
