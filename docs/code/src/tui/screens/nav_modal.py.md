# src/tui/screens/nav_modal.py

Backtick page picker. Keys 1-7 dismiss with a page id (`home`, `subscriptions`, `search`, `history`, `library`, `playlists`, `help`); the caller maps the id to a tab. `_PAGES` is the single source for both the bindings and the rows. Adding a page means adding a row here and handling the id in the caller.
