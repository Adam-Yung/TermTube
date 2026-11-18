# Where the data comes from

TermTube asks the cheapest source that can answer, and falls back one step when it cannot. Public data goes through YouTube's own web API
("InnerTube", anonymous, 0.1 to 1 s); only what truly needs yt-dlp uses yt-dlp (2 to 3 s).

| Data | Source | Account | Fallback | Cached |
|---|---|---|---|---|
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

- **Why not yt-dlp for everything?** It starts a Python extractor and a JavaScript solver per call: about 3 s for a stream URL, 3 to 14 times
  slower than InnerTube for what InnerTube can serve (`docs/guides/benchmarks.md`).
- **Why no account on InnerTube?** The web API never receives your cookies; only two yt-dlp calls do ([accounts-and-cookies.md](accounts-and-cookies.md)).
- **No RSS.** YouTube's channel feed endpoint (`feeds/videos.xml`) answered 404 for every channel, URL form and user agent from two networks
  in November 2026, so it is not used. The channel page needs nothing it provided.
- **InnerTube is undocumented.** A response shape can change without notice; parsers are small, tested on recorded fixtures, and every call falls
  back one step. A weekly canary (`scripts/canary-live.py`, GitHub `canary.yml`) checks the live shapes.
- The page size is 20 rows; Home fetches 80 at a time (the first 15 appear as soon as they arrive) and fetches more as you reach the last page.

Code: `docs/code/src/innertube.py.md`, `ytdlp.py.md`, `streams.py.md`, `cache.py.md`. Decisions: `docs/decisions/feeds-and-paging.md`,
`cookies-and-auth.md`, `playback.md`.

## Search suggestions

While typing in the search prompt (2 or more characters, after a 250 ms pause) the partial text is sent to `suggestqueries.google.com` (anonymous, no cookies, 2 s timeout, 16 KB cap) and the answers are listed under the local history matches. This is the only request made before a search is submitted. `search_suggestions: false` (or the Settings toggle) stops it. Failures show nothing.
