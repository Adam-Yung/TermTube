# src/tui/screens/mixins/feed_loader.py

Loads each tab's entries into the `VideoListPanel` and keeps the next pages ready. Design history: `docs/decisions/feeds-and-paging.md`.

## Worker group

Two exclusive groups, both `thread=True`: `feed_loader` for `_stream_view` (tab load) and `feed_extend` for `_extend_feed` (next batch). They are separate so paging to the end during the first home fetch does not cancel that fetch.

`_feed_session` (on the screen) is bumped by `_start_view`, the only entry to `_stream_view`. `_extend_feed` carries the value it started under and its result goes through `_apply_extension` / `_finish_extension` on the UI thread, which drop it when the session moved on. A tab switch, search or playlist open therefore cannot receive pages from the view before it.

`_stream_view` takes the session too and stores it in a thread-local (`_loading`). Every loader pushes to the UI through `_ui`, which checks that session on the UI thread and drops the call when the view changed. A cancelled thread still runs until its network call returns, but its late rows, error messages and modals are discarded. Loader code must call `self._ui`, never `app.call_from_thread` (`_ui` goes through `App.call_ui` and drops the call when the app has quit), except `_extend_feed`, which carries its own session.

`_worker_start`/`_worker_end` wrap the thread bodies so the header spinner counts them.

## Tabs

| Tab | Loader | Source |
|---|---|---|
| home | `_load_feed` | stash, disk cache, or `ytdlp.fetch_page_batch` |
| subscriptions | `_load_subscriptions` | `ytdlp.fetch_subscribed_channels`; rows are channels (`_is_channel`) and the detail panel switches to channel mode |
| search | `_load_search` | `ytdlp.fetch_search_batch` (50 per batch, `sort`/`kind` from the search frame) |
| history | `_load_simple_list` | `history.all_entries`, split into `page_size` pages; with `history: false` and nothing stored the list says that history is off |
| library, library:video, library:audio, playlist:`<id>` | `_load_collection` | `LibraryRailMixin._collection_entries`: `library.all_entries` filtered by kind, or `item_entries` (title from the snapshot, cache fills migrated items, download state from `library.attach_local`). A library load also pushes the rail counts. |

`FEED_TABS` (cached feeds with stash and suppression) is just `home`. `PAGED_TABS` (extendable) are `home` and `search`.

## Stash and paging model (home)

- Page size `panel.page_size` (config `rows_per_page`, default 20), batch size 80, first callback after 15 entries (`on_first_batch`).
- **Stash**: on tab switch and quit, `_save_feed_stash` keeps one page of entries the user never saw (`all_unseen_entries`), topped up from the last visited entries so the next launch's first page is always full.
- **Startup**: the stash is shown at once as page 1 (cursor usable immediately). Fresh entries are added from page 2, so the first screen never changes under the cursor. A stash on screen plus a fresh disk cache (`is_feed_fresh`) means no network call at all.
- **No stash**: the first 15 entries from `fetch_page_batch` become page 1 as they arrive; the other 65 stream in as later pages from the same session. `shown_ids` keeps the tail from duplicating the first batch.
- **Suppression**: `visible()` filters entries in the suppressed set (`cache.is_suppressed`), i.e. videos already played. The audio worker suppresses at start.
- **Extending**: feed tabs read through one `FeedCursor` per view session (`_feed_cursor`, adopted on the UI thread by `_open_cursor`, closed by `_start_view` (which also drops a waiting `_pending_show`, so the next view's first extension does not jump a page), `on_unmount`, and `ytdlp.cancel_all` through its cancel event). `_load_feed` hands it to `fetch_page_batch`, so the first 80 rows and every later batch are one lazy listing; after a cache-only start the cursor opens at the first extension and skips the held ids once. `_on_page_shown` (called by the page actions) requests an extension from the second-to-last held page on for feeds (Search: the last page). `_request_extension` keeps one extension in flight per session (`_extending_session`); paging past the end meanwhile sets `_pending_show` so the result shows when it lands. The panel footer reads `loading 80 more…`, then `N loaded`; a typed failure (`classify`) shows `⚠ message` there (and a hint when the user was waiting). `_can_extend` is false while a filter is active or the cursor is exhausted. `_fetch_next_batch` takes up to 3 rounds when suppression hides a whole batch.
- **Played videos**: `_hide_played` drops suppressed ids from Home (stash, first batch, extensions) and counts them in `_hidden_ids` (reset per load by `_reset_hidden`); the footer shows `N hidden`. `_show_played` (the `Z` key, `MainScreen.action_show_played`, Home only, a hint elsewhere) keeps them and the footer says `played shown`; the toggle reloads the view.
- **Revalidate**: for Home, a cache whose `cache.feed_age` is over `cache_ttl.home_revalidate` (600 s default) but still within the hard TTL is shown as before, then `_revalidate` reads 80 fresh rows through the cursor, rewrites the cached id list, and counts rows not already held. `panel.set_notice('↑ N new · r to refresh')` is the only visible effect; `r` clears the cache and reloads. A failure is logged and silent.
- Empty feed with no stash opens `EmptyFeedModal`. A yt-dlp extraction error on the home tab (matches `_EXTRACTION_ERRORS`) opens the yt-dlp update prompt instead of an error row.

## Limits

- Library, history and playlist views are one unpaged list; large histories render as one big page.
- `_eager_prefetch` uses a bare daemon thread (not a worker) because it must not be cancelled by tab switches or exclusive groups.

## Search loads progressively

`_load_search` passes `on_first_batch` to `ytdlp.fetch_search_batch`. The first InnerTube page (about 0.9 s) is added as page 1 and shown
at once; the remaining pages are added after the continuation requests finish, numbered after the pages the first batch used. A cache hit
never fires the callback, so `_load_search` falls back to `_show_pages` when nothing was shown early. A fully empty result with nothing
shown early goes through `_show_pages` too, which leaves the list on its empty state.

Local lists (history, library, playlist) go through `_show_pages(..., evict=False)`: they hold every page. The panel's eviction of far pages is meant for feeds that can be refetched; an evicted page of a local list would be lost.

## Filter and day headers

- `_can_extend` is false while a filter is active: a filter works on what is loaded, and extending would re-page the shown set under the cursor. `_append_pages` uses `panel.next_page_number` (pages of the full set), not `total_pages` (pages of what is shown).
- The `history` load sets `panel.set_view_options(group_by=_day_label, show_count=True)` before the pages arrive; `clear_and_set_loading` resets it on every view change.

## Search position restore

After a search load with entries, `_finish_search_load` (via `_ui`) takes the saved page and row from the `SearchStack`, shows them if the page is held, and writes the back hint into the breadcrumb.

Search extension (`_fetch_next_batch`) asks for `min(SEARCH_FETCH_COUNT, MAX_SEARCH_RESULTS - seen)` more and returns nothing once 200 are shown, so Search grows by 50 as the user pages, to 200. `_load_search` and the extension pass the current frame's sort and type.

`_load_following` fills the `following` view (a drill-down from Subscriptions, see `main_screen.py.md`) from `channel_bookmarks.entries()` with `evict=False`; an empty list says how to follow a channel (`B` on a channel page).
`_load_view` sets the list's filter matcher per view (`_matcher_for`): Library collections and playlists use `library_query.rank` (tokens, `pl:` reads `playlist.membership()` once per ranking), every other view the plain `fuzzy.rank`. `_show_pages` does not pull focus into the list while the rail has it.

Account views (`ACCOUNT_VIEWS` in `library_rail.py`: `history:yt`, `history:wl`) run `_load_account_feed`: no browser (`resolve_browser` is None, which reads no cookies) shows `_NEEDS_BROWSER`; otherwise the same `_load_feed` as Home (`fetch_page_batch`, `auth=True`, `feed_key` from the view, cache TTL `cache_ttl.<key>`), with no stash, rows copied with `_yt=True` (badge) and an honestly empty result showing `_EMPTY_ACCOUNT` instead of the yt-dlp update modal. A failed load goes through `_report_failure`: sign-in, rate limit and network errors show their `errors` message; the update prompt opens only for an `ExtractionFailed` on Home. Extension (`_fetch_next_batch`) goes through `feed_key_of(view)`, so these views page like Home.
