# src/tui/screens/search_modal.py

Search prompt. Dismisses the stripped query, or `None` for Esc or an empty query.

- Under the input a `Static` lists up to 8 candidates: `search_history.matching(typed)` (prefix, then word start, then substring, newest first). With `search_history: false` the list is empty.
- With `search_suggestions` (default on) typing also schedules a suggestion fetch: a 250 ms timer (restarted by every keystroke), then a thread worker (`suggest` group, exclusive) calling `innertube.fetch_suggestions`, for text of 2 or more characters. `_seq` is bumped on every keystroke, so an answer for older text is dropped in `_apply_suggestions`; the previous suggestions stay shown until the new ones arrive. Rows are history first (🕐), then suggestions (🔍) not already listed (case-insensitive), 8 in all. Any fetch error shows nothing.
- Up/Down highlight a row without touching the input; Enter submits the highlighted row, else the typed text. Typing resets the highlight.
- `Ctrl+D` forgets the highlighted history query. It is a priority binding because `Input` binds `ctrl+d` to delete-right.
- Recording the query is the caller's job (`MainScreen._open_search_dialog`), so cancelling never writes.
