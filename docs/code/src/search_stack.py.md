# src/search_stack.py

The Search tab's history of searches within a session (not persisted; the persistent list is `search_history`). Pure data: no UI imports.

- A frame is `query` plus the page and row (entry id) the user was on when they left it. Rows are kept by id, not index, so a restore survives re-paging.
- `push` ignores the query already on top, so re-showing the current search (tab cycling) keeps its position. The stack holds at most `MAX_DEPTH` (20) frames; the oldest is dropped.
- `take_position` hands the saved page and row out once and resets them, so a later refresh does not jump back.
- Popping is instant because `fetch_search_batch` is cache-first; the page restore only works for pages the cache holds.
