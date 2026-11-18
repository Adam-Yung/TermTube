# src/innertube.py

Stdlib-only client for two YouTube InnerTube endpoints, used where yt-dlp is too slow: `/player` for video details (~220 ms) and `/browse` for a channel's Videos tab (~600 ms for about 30 entries) and Playlists tab. Callers: `src/tui/screens/mixins/detail_focus.py` (details) and `src/tui/screens/channel_screen.py` (channel videos and playlists, falling back to `ytdlp.fetch_channel_videos` / `fetch_channel_playlists` when empty).

## Transport

`_request` (shared by `_post_json` and `fetch_suggestions`) sends requests over a per-thread keep-alive `http.client.HTTPSConnection` (default context, so certificates are verified; no cookies or auth headers). A reused connection that the server has closed fails on first use; that one failure is retried on a fresh connection, and a failure on a fresh one returns None. A non-200 status or malformed JSON returns None without a retry. Per-thread, not shared, because `http.client` connections are not thread-safe and the workers are independent. Live check 2026-11-15: `/player` 185 ms on the first call, about 118 ms after, against 157 to 219 ms per call with `urllib` (new TLS handshake each time).

## Invariants

- Metadata only. `/player` no longer returns `streamingData` without a Proof of Origin token, so stream URLs always come from yt-dlp (`src/streams.py`). See `docs/decisions/cookies-and-auth.md`.
- Unauthenticated: no cookies, WEB client context with a pinned client version. If YouTube starts rejecting the version, requests return nothing and callers fall back.
- Every failure (network, decode, unexpected shape) returns None or `[]` and logs at debug level. Callers must treat empty as "try the fallback".
- Returned dicts mimic yt-dlp info dicts (`upload_date` as `YYYYMMDD`, `uploader_id` as `@handle`). Details carry `_innertube: True`; browse entries are `_type: "url"` with `view_count_text`, `published_text` and `duration_text` as displayed.

## Limits

- Parsing follows YouTube's current `lockupViewModel` layout; a layout change yields an empty list rather than an error.
- `_CHANNEL_VIDEOS_PARAMS` is a base64 protobuf tab selector for newest-first. A popular-sort variant was not reliable, so `fetch_channel_videos` has no sort argument; the channel screen sends other sorts to yt-dlp.
- View counts parse from localized English text ("1.2M views"); other languages parse to None. The request pins `hl: en`.

## Search and channel info (optimization plan step 2)

`search_videos` posts `/search` and follows `continuationItemRenderer` tokens (`/search` with `{"continuation": token}`) up to
`_MAX_SEARCH_PAGES`. One page is about 0.9 s, so 50 results cost about 2.7 s (benchmark, `docs/guides/benchmarks.md`). Only
`videoRenderer` items are kept; playlists, shelves and channel cards (`lockupViewModel`, `gridShelfViewModel`) are dropped. Rows carry
`published_text` ("4 years ago"), not `upload_date`: search gives no exact date, and the list row falls back to the text.

`fetch_channel_info` takes a channel URL, resolves a `/@handle`, `/user/` or `/c/` URL to a `UC…` id with `/navigation/resolve_url`
(skipped when the URL already has `/channel/UC…`), then reads `/browse`. Name, description, avatar and `vanityChannelUrl` come from
`metadata.channelMetadataRenderer`. The subscriber count is not a field: it is a text node ("4.56M subscribers") found by regex anywhere
under `header`, because the header is a view-model tree that changes shape. If the count disappears, `_SUBSCRIBERS` is the place to look.
The avatar is the largest size in `avatar.thumbnails` (900 px).

Both return empty/None on any failure; `ytdlp.fetch_search_batch` and `ytdlp.fetch_channel_info` then fall back to yt-dlp. Parser tests use
trimmed recordings in `src/tests/fixtures/innertube_*.json` (recorded 2026-11-15); refresh them when a parser breaks.

## Channel playlists

`fetch_channel_playlists` posts `/browse` with `_CHANNEL_PLAYLISTS_PARAMS` (the Playlists tab) and follows the grid's trailing
`continuationItemRenderer` token (`{"continuation": token}`, items under `onResponseReceivedActions[0].appendContinuationItemsAction`) up to
`count` (80) or `_MAX_PLAYLIST_PAGES`. Live check 2026-11-15: 80 playlists in 1.0 s over 3 requests. Only `lockupViewModel` items with
`contentType` `LOCKUP_CONTENT_TYPE_PLAYLIST` are kept. Entries carry the keys the list row and `MainScreen._activate_entry` use
(`_is_playlist`, `_playlist_name`, `title`, `thumbnail`) plus `id`, `url`, `webpage_url` and `playlist_count` (from the "N videos" overlay
badge). The thumbnail is the first video's, from `collectionThumbnailViewModel`. Fixtures: `innertube_playlists.json` (first page, trimmed to
3 items and the continuation token) and `innertube_playlists_more.json` (continuation page), recorded 2026-11-15 from Google Developers.

## Search suggestions

`fetch_suggestions(query)` GETs `https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=<query>` through `_request` (same verified-TLS connection helper; only `User-Agent` and `Accept` headers, no cookies, no account). Timeout 2 s, body read capped at 16 KB (a longer reply is cut, fails to parse and the connection is dropped). `parse_suggestions` reads `[query, [suggestion, ...]]` and returns `[]` for anything else; every failure returns `[]`. Used only by `SearchModal`.
