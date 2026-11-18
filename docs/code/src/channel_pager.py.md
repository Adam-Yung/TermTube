# src/channel_pager.py

Paging state of one channel tab, kept out of `ChannelScreen` so the stop conditions are testable without a terminal. It holds the continuation token (never re-reads an earlier page), the number of entries loaded, whether a fetch is in flight, and the footer note.

- `wants_more(current_page, total_pages)` is true from the second-to-last held page on, while a token exists and no fetch runs. The first page of 30 entries is two list pages, so the next batch starts as soon as the first one is shown.
- `MAX_ENTRIES` (200) caps the tab. `finish` trims the batch that crosses it and drops the token, so the note reads "first 200 shown".
- A failed continuation arrives as an empty page with no token: paging stops for that tab until it is reloaded. The token is not kept for a retry because a transient failure and an expired token look the same.
- Touched from the UI thread only (`ChannelScreen` applies results through `call_from_thread`); there is no lock.
