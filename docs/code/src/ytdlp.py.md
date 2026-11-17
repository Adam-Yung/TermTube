# src/ytdlp.py

Owns yt-dlp option building, the flat-listing fetchers (feeds, search, channel videos, channel playlists, subscribed channels) and the process-wide cancellation registry. Stream resolution lives in `src/streams.py`, downloads in `src/downloads.py`, cookie extraction in `src/cookies.py`. History: `docs/decisions/cookies-and-auth.md`, `docs/decisions/feeds-and-paging.md`.

## Cookie policy

Cookies are a property of the call, not of the process.

| Call | Cookies | Why |
|---|---|---|
| `fetch_page_batch(auth=True)` (home feed), `fetch_subscribed_channels` | yes, via `_make_ydl(auth=True)` | Account-bound: empty or generic without them. |
| `fetch_page_batch` (default, channel videos), `fetch_search_batch`, `fetch_channel_playlists`, `fetch_channel_info` | no | Public data; keeps a search-and-browse session from reading the browser profile. |
| `resolve_stream_url` (`src/streams.py`), `download_*` (`src/downloads.py`) | no | Authenticated requests made YouTube return the degraded "tv downgraded player" response: 5 formats (storyboards plus one 360p HLS) instead of 37+ direct HTTPS formats. |
| `warmup` | no | Only loads extractors. |

Rules that follow:

- Only `_make_ydl(auth=True)` attaches a jar (`ydl.cookiejar = get_cookiejar(config)`). Never add `cookiesfrombrowser` to an options dict: yt-dlp would re-read the browser database on every `YoutubeDL`, 200-500 ms each.
- A new fetcher that needs the account goes through `_make_ydl`; anything that feeds a URL to mpv or the downloader must not.
- `browser: none` in config makes `get_cookiejar` return None, so every call runs unauthenticated.

## Options

`base_opts(skip_manifests=True)` is the single builder. With `skip_manifests` it sets `extractor_args.youtube.skip = [dash, hls]`, which saves 1-2 s per call and is right for listings. Stream resolution and downloads pass `skip_manifests=False`: with the skip, format selection picked poor formats or missed quality levels. `_flat_opts(count)` adds the lazy flat-playlist settings and the `youtubetab` `approximate_date` arg (relative dates on channel and feed entries). The Deno runtime is added only if the bundled binary exists.

## Fetch invariants

- `_extract_videos` is the shared body of `fetch_page_batch` and `fetch_search_batch`. It retries once after 2 s on an empty result (YouTube returns an empty first response now and then) and skips entries that are not 11-character video ids or are playlists/channels. The extractor window is `count + len(skip_ids)` (also the `ytsearch<N>:` fallback): `skip_ids` are dropped after extraction, so a window of `count` would return the same rows the caller already has and the second Home batch would be empty.
- Every accepted entry goes to `cache.put_video`; the id list goes to `cache.put_feed` only when it reaches `_MIN_FEED_COUNT` (15) for feeds or `_MIN_SEARCH_COUNT` (5) for search. A short result is returned but not cached as a feed.
- `_cached_entries` serves a cached feed only if at least the minimum survives `skip_ids` and missing entry files; otherwise the caller refetches.
- `on_first_batch` fires once, on the first attempt only, in the worker thread. The caller must marshal to the UI.
- Each fetch registers a cancel event; the loop checks it per entry. `cancel_all()` (called at exit) sets every event so threads blocked in iteration stop. A call already blocked inside yt-dlp's network read returns when the socket times out (30 s, 60 s for subscribed channels).
- All fetchers are blocking and meant for `@work(thread=True)` workers.

## Known limits

- `fetch_channel_videos(sort="views")` relies on the `?sort=p` URL parameter; `src/innertube.py` only supports newest-first, so the channel screen uses it for `date` only.
- Errors are logged at debug level and become empty results; callers cannot tell "empty channel" from "network failure".

Search and channel info try InnerTube first (`src/innertube.py`, no cookies, no yt-dlp import cost on the hot path) and fall back to yt-dlp when
it returns nothing. A yt-dlp fallback is logged at debug level. Channel info for a `/videos` or `/playlists` URL is normalised before the InnerTube call.
