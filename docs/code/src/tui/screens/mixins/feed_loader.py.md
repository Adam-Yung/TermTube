# src/tui/screens/mixins/feed_loader.py

Loads each tab's entries into the `VideoListPanel` and keeps the next pages ready. Design history: `docs/decisions/feeds-and-paging.md`.

## Worker group

All loading runs in group `feed_loader`, `thread=True, exclusive=True`: `_stream_view` (tab load) and `_extend_feed` (next batch). Starting either cancels the other's worker object. Consequences:

- Switching tabs cancels an in-flight extend, which is wanted.
- An extend started while the initial home fetch is still streaming (the user pages to the end very fast) cancels the rest of that fetch. A cancelled thread keeps running until its network call returns and may still push pages through `call_from_thread`; there is no session check on these paths.

`_worker_start`/`_worker_end` wrap the thread bodies so the header spinner counts them.

## Tabs

| Tab | Loader | Source |
|---|---|---|
| home | `_load_feed` | stash, disk cache, or `ytdlp.fetch_page_batch` |
| subscriptions | `_load_subscriptions` | `ytdlp.fetch_subscribed_channels`; rows are channels (`_is_channel`) and the detail panel switches to channel mode |
| search | `_load_search` | `ytdlp.fetch_search_batch` (50 results, 3 pages) |
| history | `_load_simple_list` | `history.iter_entries`, one page |
| library | `_load_simple_list` | `library.all_entries` (filesystem only) |
| playlists | `_load_playlist_index` / `_load_playlist_videos` | `playlist.py`, cached entries from `cache.get_video_raw` |

`FEED_TABS` (cached feeds with stash and suppression) is just `home`. `PAGED_TABS` (extendable) are `home` and `search`.

## Stash and paging model (home)

- Page size 20, batch size 80, first callback after 15 entries (`on_first_batch`).
- **Stash**: on tab switch and quit, `_save_feed_stash` keeps one page of entries the user never saw (`all_unseen_entries`), topped up from the last visited entries so the next launch's first page is always full.
- **Startup**: the stash is shown at once as page 1 (cursor usable immediately). Fresh entries are added from page 2, so the first screen never changes under the cursor. A stash on screen plus a fresh disk cache (`is_feed_fresh`) means no network call at all.
- **No stash**: the first 15 entries from `fetch_page_batch` become page 1 as they arrive; the other 65 stream in as later pages from the same session. `shown_ids` keeps the tail from duplicating the first batch.
- **Suppression**: `visible()` filters entries in the suppressed set (`cache.is_suppressed`), i.e. videos already played. The audio worker suppresses at start.
- **Extending**: reaching the last held page prefetches the next batch silently (`show=False`); pressing next past it shows a spinner and jumps to the new page when it arrives (`show=True`). `_fetch_next_batch` passes `skip_ids=panel.seen_ids` so new batches do not repeat held entries.
- Empty feed with no stash opens `EmptyFeedModal`. A yt-dlp extraction error on the home tab (matches `_EXTRACTION_ERRORS`) opens the yt-dlp update prompt instead of an error row.

## Limits

- Library, history and playlist views are one unpaged list; large histories render as one big page.
- `_eager_prefetch` uses a bare daemon thread (not a worker) because it must not be cancelled by tab switches or exclusive groups.

## Search loads progressively

`_load_search` passes `on_first_batch` to `ytdlp.fetch_search_batch`. The first InnerTube page (about 0.9 s) is added as page 1 and shown
at once; the remaining pages are added after the continuation requests finish, numbered after the pages the first batch used. A cache hit
never fires the callback, so `_load_search` falls back to `_show_pages` when nothing was shown early. A fully empty result with nothing
shown early goes through `_show_pages` too, which leaves the list on its empty state.
