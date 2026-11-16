# Source benchmarks

`scripts/bench-sources.py [runs]` times each rung of the source ladder (`docs/plans/2026-11-15-optimization-PLAN.md`) with anonymous
requests: no cookies, no browser profile, no media download. Run it from the network you care about; results depend on it.

## 2026-11-15, macOS, home network behind a TLS-inspecting proxy (video `dQw4w9WgXcQ`, 5 runs; yt-dlp 3 runs)

| Operation | ok | p50 ms | max ms |
|---|---|---|---|
| Thumbnail GET `i.ytimg.com` | 0 of 5 | n/a | n/a |
| oEmbed | 5 | 163 | 248 |
| Channel RSS `feeds/videos.xml` | 0 of 5 | n/a | n/a |
| InnerTube `/player` | 5 | 219 | 243 |
| InnerTube `/search` | 5 | 871 | 1115 |
| InnerTube `/browse` (channel videos) | 5 | 399 | 510 |
| yt-dlp stream resolve (`ba/b`) | 3 | 3005 | 4608 |

## What it says

- **InnerTube beats yt-dlp by 3.4x to 14x** for what it can serve: `/player` 219 ms, channel `/browse` 399 ms, `/search` 871 ms against
  3.0 s for a yt-dlp resolve. The plan's step 2 (search and channel info via InnerTube) stands.
- **RSS returned HTTP 404 for all three channels tried** (the URL is valid: a `UC…` id with `channel_id`, the documented form; a second check the same day also got nothing for the uploads-playlist form `playlist_id=UULF…`. Public reports from late October 2026, including one 404 for the Google Developers channel itself, describe a YouTube-side outage of `feeds/videos.xml`, not a client mistake; reports from May 2026 describe it as working, so it comes and goes) (Rick Astley, Google Developers, YouTube Spotlight) from this network. Do not make
  RSS the primary source for the subscription feed. Plan step 3 changes: try RSS, fall back to InnerTube `/browse` per channel, and keep a
  per-session "RSS is dead" flag so a 404 costs one request, not one per channel.
- **`i.ytimg.com` fails TLS verification here** (self-signed certificate in the chain, a proxy). `plat.download_thumbnail` already retries
  without verification for public images. The benchmark does not, so it shows 0; derived thumbnail URLs (step 1) work, but the fetch path
  keeps that retry. Timing of the thumbnail rung is not measured.
- `/search` is the slowest InnerTube call; its payload is large. Request only the first page and cache by query.

## 2026-11-15, yt-dlp stream resolve variants (`scripts/bench-sources.py 2 --streams`, 3 public videos x 2 runs)

| Variant | ok of 6 | p50 ms | max ms |
|---|---|---|---|
| baseline: fresh `YoutubeDL`, `ba/b`, manifests kept | 6 | 1246 | 2664 |
| (a) one warmed `YoutubeDL`, reused | 6 | 1220 | 1711 |
| (b) format `140/251` | 6 | 1427 | 2155 |
| skip dash and hls manifests | 6 | 1161 | 1440 |
| (c) `player_client=web_safari` | 2 | 1350 | 1907 |
| (c) `player_client=tv` | 0 | 1323 | 1413 |
| (c) `player_client=ios` | 0 | 1284 | 1605 |
| (c) `player_client=mweb` | 6 | 2438 | 3046 |

Nothing reaches the 1.5x bar: the best variant (skipping manifests, 1.07x) is inside the run-to-run spread, and it is the setting that
degraded format selection before (`docs/code/src/ytdlp.py.md`). Reusing a `YoutubeDL` saves nothing; the time is in the player request
and the JS challenge, not in object setup. `tv`, `ios` and most `web_safari` resolves fail without a PO token (ok column); `mweb` works but
is 2x slower. Nothing was wired. The baseline resolved in 1.2 s in this run against 3.0 s in the first benchmark, so the network or
YouTube's response moved more than any variant does; re-run before drawing conclusions on another network. The sample id `jNQXAC9IJRE`
was replaced by `kJQP7kiw5Fk` because it now reports "unavailable".
