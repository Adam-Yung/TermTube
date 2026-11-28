# src/sponsorblock.py

Fetches SponsorBlock skip segments for a video and caches them on disk. Called through `fetch_segments_async` from `src/tui/screens/watch_modal.py` and `src/tui/audio_controller.py` when playback starts; they apply the skips. History: `docs/decisions/playback.md` (2026-05-10 entry).

## Invariants

- Safe in worker threads. `fetch_segments_async` spawns a daemon thread and calls `on_done` there; the caller marshals to the UI.
- Disk cache at `<cache>/sb/<video_id>.json`, 24 h TTL by mtime. A failed or empty fetch is cached as `[]`, so a video with no segments (the common case) or a dead API is not re-requested for a day. Corrupt cache files read as a miss. `prune_cache` (called from app housekeeping) deletes files past the TTL, because they are otherwise only dropped when the same video is read again, and caps the directory at 300 files.
- The request timeout is 3 s: playback must not wait on this service. Any `OSError` (URL, HTTP, timeout, SSL) yields `[]`.
- The request is `/api/skipSegments/<first 4 hex chars of sha256(video id)>`, so the server sees a bucket shared with many videos, not the video being played. The response lists every video of the bucket; `_parse_segments` keeps only the exact `videoID` (`_parse_segment` reads one item). The cache stays per video id on disk.
- Segments are sorted by start. Malformed items are dropped individually.

## SSL context

The context is chosen once per process: the preference saved in `<cache>/ssl_pref` if valid, otherwise the first of `certifi`, `system` that builds (building makes no network call). If a request raises `ssl.SSLError`, the preference is dropped from memory and disk and the request retries once with a re-probed context. The point is to survive Python installs whose system certificate store is missing.

There is no unverified fallback: if neither context builds, `_cached_ssl_context` raises `OSError`, the fetch logs it at debug level and returns no segments (a stale `unverified` preference file is ignored). Sharp edge: the probe only checks that a context builds, not that it verifies this host. A `certifi` context that fails verification re-probes into the same order and builds `certifi` again, so the retry fails and the fetch returns `[]`.
