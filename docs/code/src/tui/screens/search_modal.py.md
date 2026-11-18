# src/tui/screens/search_modal.py

Search prompt. Dismisses the stripped query, or `None` for Esc or an empty query.

- Under the input a `Static` lists up to 8 candidates: `search_history.matching(typed)` (prefix, then word start, then substring, newest first). With `search_history: false` the list is empty.
- Up/Down highlight a row without touching the input; Enter submits the highlighted row, else the typed text. Typing resets the highlight.
- `Ctrl+D` forgets the highlighted history query. It is a priority binding because `Input` binds `ctrl+d` to delete-right.
- Recording the query is the caller's job (`MainScreen._open_search_dialog`), so cancelling never writes.
