# scripts/canary-live.py

Does live YouTube still look the way the parsers expect? Eight anonymous checks against youtube.com: InnerTube search (10 rows with id, title and channel id), channel videos (30 with durations), channel playlists, a playlist page (rows plus its header), a Mix read through `next`, channel info (name and subscriber count), video details, and a yt-dlp stream resolve. About 12 requests, nothing downloaded.

It is not a gate. YouTube changes without notice and datacenter addresses are sometimes blocked, so a red run means "look at the parsers", not "a commit broke the app". `.github/workflows/canary.yml` runs it weekly and on demand; run it by hand with `scripts/canary-live.py`. Exit 0 only if every check passed. Context: `docs/guides/ci.md`.
