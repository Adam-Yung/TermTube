# src/search_stack.py

The Search tab's history of searches within a session (not persisted; the persistent list is `search_history`). Pure data: no UI imports.

- A frame is `query` plus the page and row (entry id) the user was on when they left it. Rows are kept by id, not index, so a restore survives re-paging.
- `push` ignores the query already on top, so re-showing the current search (tab cycling) keeps its position. The stack holds at most `MAX_DEPTH` (20) frames; the oldest is dropped.
- `take_position` hands the saved page and row out once and resets them, so a later refresh does not jump back.
- Popping is instant because `fetch_search_batch` is cache-first; the page restore only works for pages the cache holds.

Each frame also holds `sort` (`relevance`/`date`/`views`) and `kind` (`all`/`video`/`channel`/`playlist`), so going back restores the filters too; `set_filter` changes one and drops the saved page and row (the results start again). A new query starts at relevance/all. `breadcrumb()` names an active sort or type before the back hint.
