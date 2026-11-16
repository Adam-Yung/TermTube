# Optimization plan: choosing the quickest source for each operation

Status: plan, nothing here is built. Written after the 2026-11-15 restructure (`docs/status.md`). Numbers marked *measured* come from
the decision log; the rest are estimates to be replaced by the benchmark in step 0.

## The model

Every network operation is placed on a ladder. Use the first rung that returns the fields the UI needs, and keep the next rung as the
fallback.

| Rung | Mechanism | Typical cost | Needs account cookies | Needs yt-dlp |
|---|---|---|---|---|
| 0 | Disk or RAM cache | <5 ms | no | no |
| 1 | Derive from the video id (no request) | 0 ms | no | no |
| 2 | Public static endpoint (RSS, oEmbed, `i.ytimg.com`) | 80–200 ms | no | no |
| 3 | InnerTube POST, anonymous (`/player`, `/browse`, `/search`, `/next`) | 200–600 ms (*measured* 220 ms for `/player`) | no | no |
| 4 | InnerTube POST with `SAPISIDHASH` and the cookie jar | 300–800 ms | **yes** | no |
| 5 | yt-dlp library call | 1–8 s, plus a one-off import and extractor load | optional | **yes** |

A source moves up the ladder (is adopted) only if the benchmark shows p50 at least 2x faster, it returns every field the UI reads, and the
slower rung stays wired as the fallback. A feature never depends on rung 4 or 5 unless nothing cheaper exists.

## Operation by operation

| Operation | Today | Needs account? | Target rung | Notes |
|---|---|---|---|---|
| Thumbnail for a row | URL taken from the yt-dlp entry; stubs (history, playlists) have none | no | **1** | `https://i.ytimg.com/vi/<id>/mqdefault.jpg` for lists, `hqdefault`/`maxresdefault` for the detail pane. Removes the "no thumbnail" class of bug for stub rows. |
| Video details on focus | InnerTube `/player` | no | 3 (keep) | Already optimal. |
| Title/author of a stub id | cache or id string | no | 2 | oEmbed `youtube.com/oembed?url=…&format=json`. |
| Search | yt-dlp `ytsearch` with cookies | no | **3** | InnerTube `/search` plus continuation token. Cookies add nothing the UI shows. yt-dlp stays as fallback. |
| Channel info (name, avatar, subs, description) | yt-dlp, no cookies | no | **3** | InnerTube `/browse` with the channel id; handle to id through `/navigation/resolve_url`. |
| Channel latest videos (first page) | InnerTube `/browse`, then yt-dlp | no | **2** | `feeds/videos.xml?channel_id=UC…`: 15 items with title, date, views, thumbnail, description; honors `If-None-Match`. |
| Channel videos (older pages, other sorts) | yt-dlp | no | 3 | `/browse` continuation tokens. |
| Channel playlists | yt-dlp | no | 3 | `/browse` playlists tab. |
| Subscription list | yt-dlp with cookies | **yes** | 4 (or 5) | Changes rarely: cache for 24 h and refresh on `r`. |
| Subscription feed | yt-dlp feed extraction with cookies | **only the list** | **2** | Once the list is known, fetch each channel's RSS in parallel (bounded pool of 8) and merge by date. No cookies on the hot path. |
| Home feed | yt-dlp with cookies | **yes** | **4** | InnerTube `/browse` `FEwhat_to_watch` with `SAPISIDHASH`. The disk stash already hides the latency; this removes the 3–8 s cold fetch. Spike first (see risks). |
| Stream URL (audio, video) | yt-dlp, no cookies | no | 5 (keep) | Signature and `n` challenge solving needs yt-dlp and deno. Speed it up in place, below. |
| Downloads | yt-dlp | no | 5 (keep) | Needs ffmpeg merge. |
| SponsorBlock segments | direct HTTP, 24 h disk cache | no | 2 (keep) | Switch to the hash-prefix endpoint (`/api/skipSegments/<sha256[:4]>`): the video id no longer leaves the machine. |
| History, library, playlists, queue | local | no | 0 | No network. |

### Where cookies are actually needed

Only three operations: the **home feed**, the **subscription list**, and anything age-gated or private. Everything else must run with
no cookie and no browser-profile read. Consequences:

- The cookie jar is read lazily, on the first of those three, not in a startup thread. A user who only searches and plays never pays the
  5–15 s extraction (*measured* in `docs/decisions/cookies-and-auth.md`).
- Extract only the `youtube.com` / `google.com` cookies the auth header needs (`SAPISID`, `__Secure-1PAPISID`, `__Secure-3PAPISID`, `SID`
  family). Keep them in memory only; never write them to disk.
- Re-extract on an auth failure (HTTP 401/403 or a login redirect), not on a 10-minute timer. Browser sessions last weeks.
- `cookies.get_cookiejar` keeps its single lock, so concurrent callers still trigger one extraction.

### Making the yt-dlp rung faster (stream URLs)

1. Keep one warmed `YoutubeDL` per worker thread instead of building one per call: extractor registry load is 200–400 ms (*measured*).
2. Ask for the format directly (`140`/`251` for audio) so yt-dlp skips format sorting.
3. Restrict `extractor_args: youtube: player_client` to the one client that yields direct URLs without PO tokens.
4. Prefetch on focus (already done); extend it to the row below the cursor while the user is idle.
5. **Experiment:** InnerTube `/player` with a mobile client returns direct audio URLs in ~300 ms for most videos, no deno. Behind a flag,
   with yt-dlp as fallback, and only if the 20-video benchmark shows it succeeding on at least 95 % of ids. YouTube changes this regularly,
   so it never replaces yt-dlp.

### Cold start

- `import yt_dlp` is at module top in `src/ytdlp.py`; it costs hundreds of milliseconds. Once search, channels and details go through
  InnerTube, import yt-dlp lazily and warm it in the existing background thread. Measure with `python -X importtime`.
- Keep one keep-alive HTTPS connection per host (`http.client.HTTPSConnection`, thread-local). Each `urlopen` today pays a TLS handshake.
- `src/main.py` imports `textual_image` before Textual starts for terminal detection; keep that, but nothing else heavy should precede
  the first paint.

## Code structure follow-ups

- **App-level `AudioController`.** Audio state lives in `MainScreen` (`AudioPlayerMixin`) and `ChannelScreen` finds it by scanning
  `screen_stack`. Move it to an object on `TermTubeApp` that screens subscribe to through `PlayerStateUpdated`. Removes the coupling and
  lets any screen own a mini-player.
- **One video launch path.** After the restructure `WatchModal` and the audio worker share `streams.resolve_for_playback`,
  `streams.re_resolve` and `sponsorblock.fetch_segments_async`. The remaining duplicate is the retry loop and mpv spawn; unify as
  `player.run_mpv_with_retries`.
- **Typed entries.** Rows are untyped dicts with ad-hoc `_is_channel`, `_is_playlist`, `_local_path` keys. A small `TypedDict` per row kind
  would turn typos into test failures.
- **Lint in the gate.** `ruff` is not installed here; install it (with approval) and add `ruff check` to `scripts/verify.sh`.
- **Config schema.** `Config._data` is reached into from three places (`thumbnail_warning_dismissed`). Add `Config.set()`.

## Steps

0. **Benchmark** (done 2026-11-15): `scripts/bench-sources.py`; results in `docs/guides/benchmarks.md`. Re-run before adopting each rung.
1. Rung 1 thumbnails from the id (smallest change, kills stub-row bugs). Tests: URL derivation, fallback order.
2. InnerTube search and channel info/playlists, yt-dlp as fallback. Tests: parser fixtures from recorded JSON; no network in the suite.
3. Subscription feed and channel first page: try RSS, fall back to InnerTube `/browse` per channel. RSS returned 404 for every channel in the
   2026-11-15 benchmark, so it needs a per-session dead flag. Tests: Atom fixtures, 404 fallback, merge order.
4. Lazy cookies and narrowed jar; re-extract on auth failure.
5. Spike: authenticated InnerTube home feed. Go only if the cookie risk below is acceptable.
6. Speed-ups for the yt-dlp rung (warm instance, direct format, client pinning).
7. Cold-start pass (lazy yt-dlp import, keep-alive connections).
8. `AudioController`, unified mpv launch path, typed entries.

## Risks

- **InnerTube and RSS are undocumented.** Response shapes change. Keep parsers small, fixture-tested, and every call falls back one rung.
- **`SAPISIDHASH` requests impersonate the browser session.** They are as account-bound as the cookies the app already reads, but they are
  new traffic from this app to an authenticated endpoint. Decide before step 5; a refusal leaves the home feed on yt-dlp.
- **Rate limits.** The RSS fan-out for subscriptions is N requests. Bound the pool, honor `ETag`, cache for 10 minutes.
- **Stale caches hide regressions.** Every adopted source logs its rung at debug level so `termtube --debug` shows which one answered.
