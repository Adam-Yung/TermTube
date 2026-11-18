# src/tui/screens/settings_modal.py

Settings in six sections (Playback, Downloads, Data, Account, Display, Config file) as one `ListView` with disabled section headers and one `_Row` per `FIELDS` entry (`docs/code/src/tui/settings_fields.py.md`). Each change writes `config` and calls `Config.save()` at once; there is no Save button (`docs/decisions/config.md`).

- Keys: `j`/`k` move (headers and the read-only "In use" line are disabled, so the cursor skips them), `Tab`/`Shift+Tab` jump a section, `Enter` changes the row, `Space` does the same, `Backspace` resets the row to its default, `Esc` closes. `d` is bound globally in the lists, so reset is on `Backspace`; Settings is a modal, so nothing underneath sees the key.
- While a text or number field is open, `check_action` blocks the list actions, so `j`, `k`, `Space` and `Backspace` type into the field. `Esc` cancels the edit first and closes the dialog on the second press.
- A refused value stays in the open field with a red one-line reason. The status line under the list also reports saves, and says so when `save()` returned False (the change then lasts until quit).
- Choices reuse `QualityModal` with `choices`, `title` and `current` (the picker the `V` key uses); the browser picker lists `auto`, `none`, detected browsers, then supported-but-missing ones labelled "(not found)".
- Actions need a second `Enter` on the same row to confirm (clear cache, watch history, search history); moving the cursor disarms. "Reload from disk" runs at once: `Config.reload()` returns an error string and leaves memory untouched on a YAML or read failure, and a success re-applies the theme and refreshes every row. Cache clearing runs in the `settings_clear` worker group because it unlinks many files.
- Theme: swaps the `theme-*` class on the app, then re-renders widgets that baked the accent colour into Rich markup (`VideoListItem`, `ActionBar`); pure TCSS cannot reach those (`theme.tcss.md`). Reload applies it too.
- `cache_ttl` edits reach the live `Cache` because `Config` mutates its `cache_ttl` dict in place (the cache holds the same object).
- `rows_per_page` takes effect at the next list load (`VideoListPanel.clear_and_set_loading`); the row's note says so.

Known limit: no `/` search inside Settings yet; the dialog is a single scrolling list of about 26 rows.
