# src/tui/screens/mixins/feed_loader.py

Loads each tab's entries into the `VideoListPanel` and keeps the next pages ready. Design history: `docs/decisions/feeds-and-paging.md`.

## Worker group

Two exclusive groups, both `thread=True`: `feed_loader` for `_stream_view` (tab load) and `feed_extend` for `_extend_feed` (next batch). They are separate so paging to the end during the first home fetch does not cancel that fetch.

`_feed_session` (on the screen) is bumped by `_start_view`, the only entry to `_stream_view`. `_extend_feed` carries the value it started under and its result goes through `_apply_extension` / `_finish_extension` on the UI thread, which drop it when the session moved on. A tab switch, search or playlist open therefore cannot receive pages from the view before it.

`_stream_view` takes the session too and stores it in a thread-local (`_loading`). Every loader pushes to the UI through `_ui`, which checks that session on the UI thread and drops the call when the view changed. A cancelled thread still runs until its network call returns, but its late rows, error messages and modals are discarded. Loader code must call `self._ui`, never `app.call_from_thread`, except `_extend_feed`, which carries its own session.

`_worker_start`/`_worker_end` wrap the thread bodies so the header spinner counts them.

## Tabs

| Tab | Loader | Source |
|---|---|---|
| home | `_load_feed` | stash, disk cache, or `ytdlp.fetch_page_batch` |
| subscriptions | `_load_subscriptions` | `ytdlp.fetch_subscribed_channels`; rows are channels (`_is_channel`) and the detail panel switches to channel mode |
| search | `_load_search` | `ytdlp.fetch_search_batch` (50 per batch, `sort`/`kind` from the search frame) |
| history | `_load_simple_list` | `history.all_entries`, split into `PAGE_SIZE` pages |
| library | `_load_simple_list` | `library.all_entries` (filesystem only) |
| playlists | `_load_playlist_index` / `_load_playlist_videos` | `playlist.py` rows built by `playlist_tools.index_entries` / `item_entries` (title from the snapshot, cache fills migrated items); was: cached entries from `cache.get_video_raw` |

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

Local lists (history, library, playlist index and view) go through `_show_pages(..., evict=False)`: they hold every page. The panel's eviction of far pages is meant for feeds that can be refetched; an evicted page of a local list would be lost.

## Filter and day headers

- `_can_extend` is false while a filter is active: a filter works on what is loaded, and extending would re-page the shown set under the cursor. `_append_pages` uses `panel.next_page_number` (pages of the full set), not `total_pages` (pages of what is shown).
- The `history` load sets `panel.set_view_options(group_by=_day_label, show_count=True)` before the pages arrive; `clear_and_set_loading` resets it on every view change.

## Search position restore

After a search load with entries, `_finish_search_load` (via `_ui`) takes the saved page and row from the `SearchStack`, shows them if the page is held, and writes the back hint into the breadcrumb.

Search extension (`_fetch_next_batch`) asks for `min(SEARCH_FETCH_COUNT, MAX_SEARCH_RESULTS - seen)` more and returns nothing once 200 are shown, so Search grows by 50 as the user pages, to 200. `_load_search` and the extension pass the current frame's sort and type.
