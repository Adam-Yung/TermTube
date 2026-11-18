# src/innertube.py

Stdlib-only client for two YouTube InnerTube endpoints, used where yt-dlp is too slow: `/player` for video details (~220 ms) and `/browse` for a channel's tabs (Videos about 600 ms for 30 entries, Shorts, Live, Playlists) with continuation pages. Callers: `src/tui/screens/mixins/detail_focus.py` (details) and `src/tui/screens/channel_screen.py` (channel videos and playlists, falling back to `ytdlp.fetch_channel_videos` / `fetch_channel_playlists` when empty).

## Transport

`_request` (shared by `_post_json` and `fetch_suggestions`) sends requests over a per-thread keep-alive `http.client.HTTPSConnection` (default context, so certificates are verified; no cookies or auth headers). A reused connection that the server has closed fails on first use; that one failure is retried on a fresh connection, and a failure on a fresh one returns None. A non-200 status or malformed JSON returns None without a retry. Per-thread, not shared, because `http.client` connections are not thread-safe and the workers are independent. Live check 2026-11-15: `/player` 185 ms on the first call, about 118 ms after, against 157 to 219 ms per call with `urllib` (new TLS handshake each time).

## Invariants

- Metadata only. `/player` no longer returns `streamingData` without a Proof of Origin token, so stream URLs always come from yt-dlp (`src/streams.py`). See `docs/decisions/cookies-and-auth.md`.
- Unauthenticated: no cookies, WEB client context with a pinned client version. If YouTube starts rejecting the version, requests return nothing and callers fall back.
- Every failure (network, decode, unexpected shape) returns None or `[]` and logs at debug level. Callers must treat empty as "try the fallback".
- Returned dicts mimic yt-dlp info dicts (`upload_date` as `YYYYMMDD`, `uploader_id` as `@handle`). Details carry `_innertube: True`; browse entries are `_type: "url"` with `view_count_text`, `published_text` and `duration_text` as displayed.

## Limits

- Parsing follows YouTube's current `lockupViewModel` layout; a layout change yields an empty list rather than an error.
- The Videos selector is newest-first. A popular-sort variant was not reliable, so no function here takes a sort; the channel screen sends other sorts to yt-dlp.
- View counts parse from localized English text ("1.2M views"); other languages parse to None. The request pins `hl: en`.

## Search and channel info (optimization plan step 2)

`search(query, sort=, kind=)` posts `/search` and follows `continuationItemRenderer` tokens (`/search` with `{"continuation": token}`) up to
`_MAX_SEARCH_PAGES`. One page is about 0.9 s, so 50 results cost about 2.7 s (benchmark, `docs/guides/benchmarks.md`). `videoRenderer`, `channelRenderer`, `playlistRenderer` and playlist `lockupViewModel` rows become entries (`_is_channel` / `_is_playlist` rows as on Subscriptions and the channel Playlists tab); shelves and ads are dropped. `_MAX_SEARCH_PAGES` is 12 (about 200 results). `search_params(sort, kind)` builds the `params` blob (sent with the first request only): `CAI=` date, `CAM=` views, `EgIQAQ==` video, `EgIQAg==` channel, `EgIQAw==` playlist, and the two messages joined for a combination. Fixture `innertube_search_mixed.json` is a hand-trimmed recorded-shape page. Rows carry
`published_text` ("4 years ago"), not `upload_date`: search gives no exact date, and the list row falls back to the text.

`fetch_channel_info` takes a channel URL, resolves a `/@handle`, `/user/` or `/c/` URL to a `UC…` id with `/navigation/resolve_url`
(skipped when the URL already has `/channel/UC…`), then reads `/browse`. Name, description, avatar and `vanityChannelUrl` come from
`metadata.channelMetadataRenderer`. The subscriber count is not a field: it is a text node ("4.56M subscribers") found by regex anywhere
under `header`, because the header is a view-model tree that changes shape. If the count disappears, `_SUBSCRIBERS` is the place to look.
The avatar is the largest size in `avatar.thumbnails` (900 px).

Both return empty/None on any failure; `ytdlp.fetch_search_batch` and `ytdlp.fetch_channel_info` then fall back to yt-dlp. Parser tests use
trimmed recordings in `src/tests/fixtures/innertube_*.json` (recorded 2026-11-15); refresh them when a parser breaks.

## Channel tabs and pages

`fetch_channel_page(channel_id, tab, token)` is the one /browse reader for the channel tabs (`CHANNEL_TABS`: videos, shorts, live, playlists). The first request sends `browseId` plus the tab's `_CHANNEL_TAB_PARAMS` selector (a base64 protobuf holding the tab name); every later request sends only `{"continuation": token}`. `_browse_items` reads the rich grid (videos, shorts, live) or the playlist grid from a first response, or `onResponseReceivedActions[0].appendContinuationItemsAction` from a continuation. `_next_token` takes the trailing `continuationItemRenderer`. The result is a `ChannelPage(entries, token)`; every failure is an empty page with no token. The channel screen keeps the token and asks for the next page itself (`src/channel_pager.py`); `fetch_channel_videos` (first page of Videos) remains for `scripts/canary-live.py` and `scripts/bench-sources.py`.

- **[verify live]** The `shorts` and `live` selectors follow the pattern of the recorded `videos` and `playlists` ones but were not recorded themselves, and the Shorts parser (`shortsLockupViewModel`: `onTap...reelWatchEndpoint.videoId`, `overlayMetadata.primaryText` and `secondaryText`, `thumbnail.sources`) and the live badge (`LIVE`, "N watching") are written from the documented shape. Fixtures `innertube_channel_videos*.json` and `innertube_channel_shorts.json` are hand-written, not recorded. Replace them with trimmed recordings and run `scripts/canary-live.py`.
- Live rows set `is_live`. A Live-tab row for a finished stream carries "Streamed N days ago" in `published_text`.
- `fetch_channel_info` also returns `video_count` (the "442 videos" header text), `joined` (a header text starting "Joined"; **[verify live]**: the current layout may only show it in the About popup, a separate request this app does not make, so it can be empty) and `tabs` (which of `CHANNEL_TABS` have a tab title in the first response; the screen hides the rest).
- Popular and oldest sorts (the filter chips in the rich grid header) are not read: see the 2026-11-18 entry in `docs/decisions/feeds-and-paging.md`.

`fetch_playlist_page(playlist_id, token)` is the same shape for a playlist: `browseId` is `VL` plus the id, items are `playlistVideoListRenderer.contents` (`_browse_items` finds them), each `playlistVideoRenderer` becomes a video entry with the uploader and `channel_id` from `shortBylineText`. Rows without a `videoId` (deleted or private videos) are dropped. **[verify live]**: written from the documented shape.

## Channel playlists

`fetch_channel_playlists` calls `fetch_channel_page(..., "playlists")` and follows the grid's continuation up to `count` (80) or `_MAX_PLAYLIST_PAGES`. Live check 2026-11-15: 80 playlists in 1.0 s over 3 requests. Only `lockupViewModel` items with
`contentType` `LOCKUP_CONTENT_TYPE_PLAYLIST` are kept. Entries carry the keys the list row and `MainScreen._activate_entry` use
(`_is_playlist`, `_playlist_name`, `title`, `thumbnail`) plus `id`, `url`, `webpage_url` and `playlist_count` (from the "N videos" overlay
badge). The thumbnail is the first video's, from `collectionThumbnailViewModel`. Fixtures: `innertube_playlists.json` (first page, trimmed to
3 items and the continuation token) and `innertube_playlists_more.json` (continuation page), recorded 2026-11-15 from Google Developers.

## Search suggestions

`fetch_suggestions(query)` GETs `https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=<query>` through `_request` (same verified-TLS connection helper; only `User-Agent` and `Accept` headers, no cookies, no account). Timeout 2 s, body read capped at 16 KB (a longer reply is cut, fails to parse and the connection is dropped). `parse_suggestions` reads `[query, [suggestion, ...]]` and returns `[]` for anything else; every failure returns `[]`. Used only by `SearchModal`.
