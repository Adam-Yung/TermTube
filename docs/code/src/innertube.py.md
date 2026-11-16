# src/innertube.py

Stdlib-only client for two YouTube InnerTube endpoints, used where yt-dlp is too slow: `/player` for video details (~220 ms) and `/browse` for a channel's Videos tab (~600 ms for about 30 entries). Callers: `src/tui/screens/mixins/detail_focus.py` (details) and `src/tui/screens/channel_screen.py` (channel videos, falling back to `ytdlp.fetch_channel_videos` when empty).

## Invariants

- Metadata only. `/player` no longer returns `streamingData` without a Proof of Origin token, so stream URLs always come from yt-dlp (`src/streams.py`). See `docs/decisions/cookies-and-auth.md`.
- Unauthenticated: no cookies, WEB client context with a pinned client version. If YouTube starts rejecting the version, requests return nothing and callers fall back.
- Every failure (network, decode, unexpected shape) returns None or `[]` and logs at debug level. Callers must treat empty as "try the fallback".
- Returned dicts mimic yt-dlp info dicts (`upload_date` as `YYYYMMDD`, `uploader_id` as `@handle`). Details carry `_innertube: True`; browse entries are `_type: "url"` with `view_count_text`, `published_text` and `duration_text` as displayed.

## Limits

- Parsing follows YouTube's current `lockupViewModel` layout; a layout change yields an empty list rather than an error.
- `_CHANNEL_VIDEOS_PARAMS` is a base64 protobuf tab selector for newest-first. A popular-sort variant was not reliable, so `fetch_channel_videos(sort="views")` returns newest-first; the channel screen only calls it with `date`. The `sort` parameter is kept for signature parity.
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
