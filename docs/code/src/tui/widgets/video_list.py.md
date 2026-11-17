# src/tui/widgets/video_list.py

The paged list. Entries live in `_pages` (page number to entries, `PAGE_SIZE` = 20); the `ListView` shows one page. Everything that fetches (`FeedLoaderMixin`, `ChannelScreen`) pushes pages in; this widget never fetches.

## Invariants

- **Dedup by id across pages.** `_seen_ids` drops an entry already held in any page. Entries without an id are never deduplicated. Evicting a page removes its ids, so they can come back.
- **Memory cap.** Beyond 30 pages, pages farther than 2 from the current one are evicted, oldest first, unless the caller passes `evict=False` (local lists, which cannot refetch).
- **Paging contract.** `load_page` returns False when the page is not held. `can_go_next`/`can_go_prev` are False while loading. `show_next_page_loading` bumps `_current_page` to the page about to arrive and shows the spinner; the caller then calls `add_entries` and `load_page` (see `FeedLoaderMixin._append_pages`).
- **Stash.** `_max_visited_page` is the highest page the user opened. `all_unseen_entries` returns pages above it; `visited_entries` returns every held page. `FeedLoaderMixin._save_feed_stash` builds the next launch's first page from them (see the stash/paging model in `docs/code/src/tui/screens/mixins/feed_loader.py.md`).
- **Selection message.** `ListView.Highlighted` becomes `VideoListPanel.Selected` (cursor moved); Enter and double-click become `Activated`. A single click on the highlighted row activates; on another row it only moves the highlight.
- `update_entry_by_id` swaps an enriched entry into its page and rebuilds the visible row markup, so metadata that arrives after the row was drawn shows up without reloading the page. `settings_modal.py` also rebuilds rows (`_build_markup`) after a theme change.

## Row markup

`VideoListItem._build_markup` handles four row kinds: channel (Subscriptions), playlist, library item (badges from `_local_type`/`_has_audio`) and video. The `_is_*` and `_local_*` keys are set by the loaders and `library.py`.
