# src/search_history.py

`search_history.json` through `JsonStore`: a list of `{q, at}` records, newest first, at most 100, unique by `casefold`. Writes are deferred off the calling thread (`update(defer=True)`); `clear` writes at once.

- `add` is a no-op when `config.search_history_enabled` is false (only a literal `false` disables).
- `matching` reuses `fuzzy.rank_strings`, so ranking matches the list filter; ties keep recency order.
- Not shared with the search stack (`src/search_stack.py`), which is per session.
