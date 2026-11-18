# src/tui/library_delete.py

The Library tab's delete handler, registered in `MainScreen._removals()` under `"library"` (`removal(config)`).

- `ask(entries)` builds the inline question for the shared `D` flow and the key-to-choice map. One entry with both forms: `v video / a audio /
  b both / e entry only / N cancel`, with each form's size. One form: `y / N` (deletes it). A row whose file is missing: `Remove "<title>" (file
  missing)?` (choice `entry_only`). Marked rows: `Delete N items (X MB)?  y / N`, which means `both` for each.
- `removal(config)` returns a `Removal` whose `remove` calls `library.safe_delete` for every target with `config.video_dir` and
  `config.audio_dir` as the roots, and returns the targets that had no failures. `permanent=True`: no undo, and the notice says the files are gone.
  `reload` returns `library.all_entries`, so the list re-pages from the index after the delete.
