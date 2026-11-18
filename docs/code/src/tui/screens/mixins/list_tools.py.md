# src/tui/screens/mixins/list_tools.py

Mark, remove and undo for `MainScreen` (`ChannelScreen` has only the filter). Marks live in `VideoListPanel`; this mixin owns the removal question and the undo slot.

## Extension point: `_removals()`

A dict from tab id to `Removal(remove, restore, reload, noun)`. `remove(entries)` deletes and returns copies of the removed records; `restore(records)` puts them back; `reload()` returns the tab's entries as they are now (the panel re-pages from it, so day headers, the filter and the page stay right). Only `history` has one. A tab without an entry answers `D` with a hint from `_NOT_REMOVABLE` (or a generic line); Library and Playlists get theirs in their own phases.

## Flow

- `D` targets the marked rows, else the highlighted row, and shows the question in the action bar (`ActionBar.show_prompt`). `_pending_remove` holds the targets.
- `on_key` runs while a question is open: `y` confirms, any other key cancels, and the event is stopped and default-prevented so it reaches no binding (a stray `j` or `q` must not act). The mixin precedes `ListNavMixin` in the MRO so its `on_key` runs first.
- After removal the cursor goes to the next surviving row (else the previous one) on whichever page it now lives.
- `_undo` keeps one removal for 30 s (`time.monotonic`). `u` restores it even after a tab change; the list is re-paged only when that tab is showing. Records are copies: `history.all_entries()` shares its dicts with the store.
