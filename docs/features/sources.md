# Where the data comes from

TermTube asks the cheapest source that can answer, and falls back one step when it cannot. Public data goes through YouTube's own web API
("InnerTube", anonymous, 0.1 to 1 s); only what truly needs yt-dlp uses yt-dlp (2 to 3 s).

## The source ladder

Each operation takes the first rung that returns the fields the UI reads, and keeps the next as fallback:

1. disk or memory cache;
2. derived from the video id, no request (thumbnail URLs);
3. a public static endpoint (`i.ytimg.com`, SponsorBlock);
4. InnerTube, anonymous;
5. yt-dlp.

A faster source is adopted only if the benchmark (`scripts/bench-sources.py`) shows it clearly faster (p50 at least 2x for a new rung, 1.5x for a
yt-dlp variant), it returns every field the UI reads, and the slower one stays wired as fallback. No authenticated InnerTube.

## Sources by data

| Data | Source | Account | Fallback | Cached |
|---|---|---|---|---|
| **YouTube history** (History tab, `Y`) | yt-dlp, `youtube.com/feed/history` | cookies (browser) | a message (browser signed out, or history paused) | id list 10 min (`cache_ttl.yt_history`); read-only, same loader and paging as Home |
| **Watch Later** (History tab, `Y`) | yt-dlp, `youtube.com/playlist?list=WL` | cookies (browser) | a message | id list 10 min (`cache_ttl.yt_watchlater`); read-only, same loader as Home |
| **Home feed** | yt-dlp, flat listing of `youtube.com` | cookies (browser) | none (an empty feed explains itself) | id list 1 h (`cache_ttl.home`) plus a one-page stash for instant start |
| **Subscription list** | yt-dlp, `feed/channels` | cookies | none | about 1 h |
| **Search** | InnerTube `/search`; first page after one request, first 50 results, then 50 more each time you page, up to 200; `s` sort (relevance / date / views) and `t` type (all / video / channel / playlist) via the request `params` | no | yt-dlp `ytsearchN:` (plain search only) | by query, sort and type, 30 min |
| **Channel videos** (newest first) | InnerTube `/browse`, about 30 with durations | no | yt-dlp; other sorts (most viewed) always use yt-dlp | no |
| **Channel playlists** | InnerTube `/browse` playlists tab, following continuations up to 80 | no | yt-dlp | no |
| **Channel info** (name, subscribers, avatar) | InnerTube `/navigation/resolve_url` + `/browse` | no | yt-dlp | metadata cache, 24 h |
| **Video details** (description, views, likes) | InnerTube `/player`, metadata only, when you pause on a row | no | none (the row keeps its basic fields) | per video, 24 h |
| **Stream URLs** (audio, video) | yt-dlp (needs Deno to solve YouTube's JavaScript challenge) | **no, on purpose** | retry, re-resolve | in memory, about 5 h, prefetched on focus |
| **Downloads** | yt-dlp, then ffmpeg | no | none | files on disk |
| **Skip segments** | the SponsorBlock API (`sponsor.ajay.app`), 3 s timeout, sends only the first 4 hex chars of the video id's SHA-256 | no | none (no skipping) | 24 h |
| **Thumbnails** | `i.ytimg.com`, derived from the video id when a row has none | no | placeholder | JPEGs on disk |
| **Library, History, Playlists** | your disk | no | | |

Notes:

- **Subscriptions lists channels, not a video feed** (owner's choice): `Enter` opens the channel page.
- **Why not yt-dlp for everything?** It starts a Python extractor and a JavaScript solver per call: about 3 s for a stream URL, 3 to 14 times
  slower than InnerTube for what InnerTube can serve (`docs/guides/benchmarks.md`).
- **Why no account on InnerTube?** The web API never receives your cookies; only the yt-dlp calls for the account feeds (Home, subscriptions, YouTube history, Watch Later) do ([accounts-and-cookies.md](accounts-and-cookies.md)).
- **No RSS.** YouTube's channel feed endpoint (`feeds/videos.xml`) answered 404 for every channel, URL form and user agent from two networks
  in November 2026, so it is not used. The channel page needs nothing it provided.
- **InnerTube is undocumented.** A response shape can change without notice; parsers are small, tested on recorded fixtures, and every call falls
  back one step. A weekly canary (`scripts/canary-live.py`, GitHub `canary.yml`) checks the live shapes.
- The page size is 20 rows; Home fetches 80 at a time (the first 15 appear as soon as they arrive) and (a cache older than `cache_ttl.home_revalidate`, 10 min, is shown at once and re-read behind it; new items are announced in the footer as `↑ N new · r to refresh`, never inserted under the cursor) (Home hides videos you already played: the footer counts them as `N hidden` and `Z` shows or hides them) fetches the next 80 when you reach the second-to-last page, continuing the same open yt-dlp listing instead of re-reading from the top (History on YouTube and Watch Later work the same). The footer shows `loading 80 more…` and then the new total.

Code: `docs/code/src/innertube.py.md`, `ytdlp.py.md`, `streams.py.md`, `cache.py.md`. Decisions: `docs/decisions/feeds-and-paging.md`,
`cookies-and-auth.md`, `playback.md`.

## Search suggestions

While typing in the search prompt (2 or more characters, after a 250 ms pause) the partial text is sent to `suggestqueries.google.com` (anonymous, no cookies, 2 s timeout, 16 KB cap) and the answers are listed under the local history matches. This is the only request made before a search is submitted. `search_suggestions: false` (or the Settings toggle) stops it. Failures show nothing.

## Failures

A failed fetch is a typed error (`src/errors.py`), not an empty list; an honestly empty feed still shows the empty-feed dialog (Home) or "Nothing here" (account sources). The list shows `⚠ Network error · r to retry`, `⚠ YouTube is rate limiting this IP · try again in a minute`, or the sign-in message (Settings `,`, then `r`); only a real extraction failure on Home opens the yt-dlp update prompt. InnerTube retries once after about 1 s on 429, 5xx or a failed connection; search then falls back to yt-dlp. The debug log pane says which source answered (`cache`, `innertube`, `yt-dlp`). Local tabs (History, Library, playlists) never touch the network.
