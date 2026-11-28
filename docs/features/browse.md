# Browsing: Home, Subscriptions, Search, channels, playlists

> Verified: 2026-11-28 · Sources: `src/tui/screens/channel_screen.py`, `src/tui/screens/mixins/channel_content.py`, `src/tui/screens/mixins/list_sources.py`, `src/tui/screens/mixins/search_tab.py`, `src/search_stack.py`, `src/channel_pager.py`, `src/channel_bookmarks.py`
> Serves: `browse`
> Owns: `src/channel_*.py`, `src/search_history.py`, `src/search_stack.py`, `src/fuzzy.py`, `src/tui/urls.py`, `src/tui/screens/channel_*.py`, `src/tui/screens/search_modal.py`, `src/tui/screens/sort_modal.py`, `src/tui/screens/empty_feed_modal.py`, `src/tui/screens/ytdlp_update_modal.py`, `src/tui/screens/mixins/channel_*.py`, `src/tui/screens/mixins/feed_*.py`, `src/tui/screens/mixins/list_sources.py`, `src/tui/screens/mixins/search_tab.py`, `src/tui/screens/mixins/subscription_rows.py`, `src/tui/widgets/channel_info_panel.py`

## What it does

- **Home** (`F1`): the signed-in feed, extended as you page. Played videos are hidden (`Z` shows them). Playlist and Mix rows appear.
- **Subscriptions** (`F2`): the account's channel list, and **Following**, the channels followed locally with `B` (works with `browser: none`).
- **Search** (`F3`, `/`): results with sort (`s`) and type (`t`), a session stack of 20 searches (Backspace), 100 remembered queries and suggestions.
- **Channel page**: Videos, Shorts, Live and Playlists tabs, follow, sort, description. A playlist row opens in place.
- **Playlist page**: `Enter` on a playlist or Mix row from Search or Home.

## How it works

`FeedLoaderMixin` picks a loader per view (`views.py` names the views). Feeds go through one lazy `FeedCursor`; the other views are
`ListSourcesMixin`. Each load runs in a worker and drops its result when the view's session counter has moved on. `ChannelScreen` is pushed over the
main screen; `ChannelContentMixin` fetches its pages and `ChannelPager` holds the continuation token. Where each kind of data comes from:
[sources.md](sources.md).

## Code

`src/tui/screens/channel_screen.py`, `src/tui/screens/mixins/feed_loader.py`, `src/tui/screens/mixins/feed_paging.py`, `src/tui/screens/mixins/list_sources.py`,
`src/tui/screens/mixins/search_tab.py`, `src/tui/screens/mixins/channel_content.py`, `src/search_stack.py`, `src/search_history.py`, `src/channel_bookmarks.py`.
Mirrors under `docs/code/`; decisions in `docs/decisions/feeds-and-paging.md` and `docs/decisions/playlist-page.md`.

## Rules that must hold

- A worker's late result never reaches a view the user has left.
- Rows under the cursor never move behind the user's back (fresh Home rows are only announced).
- Account feeds are the only calls that use cookies ([accounts-and-cookies.md](accounts-and-cookies.md)).
- A failed fetch shows its typed message, not an empty list.

## Limits

- The signed-in Home (paging, playlist and Mix rows) and YouTube history are not verified live: they need the owner's browser.
- Search stops at 200 results; a channel's videos and a playlist page stop at 200; channel playlists at 80.
- Popular and oldest sorts go through yt-dlp and return one batch.

## How to check it

`src/tests/tui/test_feed_extend.py`, `src/tests/tui/test_search_back.py`, `src/tests/tui/test_channel_paging.py`, `src/tests/tui/test_playlist_page.py`, `src/tests/tui/test_home_revalidate.py`.
Live: [../guides/morning-checklist.md](../guides/morning-checklist.md).
