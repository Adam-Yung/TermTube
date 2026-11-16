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
- **RSS returned HTTP 404 for all three channels tried** (Rick Astley, Google Developers, YouTube Spotlight) from this network. Do not make
  RSS the primary source for the subscription feed. Plan step 3 changes: try RSS, fall back to InnerTube `/browse` per channel, and keep a
  per-session "RSS is dead" flag so a 404 costs one request, not one per channel.
- **`i.ytimg.com` fails TLS verification here** (self-signed certificate in the chain, a proxy). `plat.download_thumbnail` already retries
  without verification for public images. The benchmark does not, so it shows 0; derived thumbnail URLs (step 1) work, but the fetch path
  keeps that retry. Timing of the thumbnail rung is not measured.
- `/search` is the slowest InnerTube call; its payload is large. Request only the first page and cache by query.
