# src/tui/screens/mixins/list_sources.py

The non-feed views: subscriptions, following, search, local history, Library collections and playlists. All run on the loader thread. A new list source is an entry in `_source_loader` (feeds go in `FeedLoaderMixin._view_loader`).

- Search shows its first batch at once; the rest is paged after it, then the saved position is restored.
- Local lists pass `evict=False`: they cannot refetch a dropped page.
- `matcher_for` gives Library views the `key:value` filter.

- `local` (the Local tab) is loaded by `LocalTabMixin._load_local` ([local_tab.py.md](local_tab.py.md)); it is not a Library view, so its filter is plain text.
