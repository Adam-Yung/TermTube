# src/tui/screens/mixins/feed_paging.py

Next-batch loading for feeds and search (`feed_extend` group), split from the loader. `feed_loader.py.md` describes when it runs.

- One extension per view at a time; a second request only makes the pending result show when it lands.
- Home takes up to three cursor batches until one yields a row not already played.
- `_adopt_loader_session` must run first on the thread, so `_ui` calls made while fetching (opening a cursor, counting hidden rows) are dropped after a view change.
