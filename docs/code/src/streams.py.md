# src/streams.py

Resolves a video id to direct stream URLs with yt-dlp, caches them, and hides CDN warm-up latency before mpv opens them. Callers: the focus-dwell prefetch worker, the play path (`resolve_for_playback`), and the playback retry (`re_resolve`). History: `docs/decisions/playback.md`, `docs/decisions/cookies-and-auth.md`.

## Invariants

- No cookies, ever. Authenticated requests got YouTube's degraded "tv downgraded player" response (HLS only). Options come from `base_opts(skip_manifests=False)`: DASH/HLS data is required for format selection. Audio ids resolve in about 1.9 s, video in 2.4 s.
- The URL cache is in memory only: CDN URLs are session-bound and expire in about 6 h (TTL 5 h), 40 entries, oldest evicted. Key is `"<video_id>:<format_spec>"`. All access holds `_stream_cache_lock`.
- Prefetch resolves the audio format only, right after the InnerTube metadata fetch, so most listens find a cached URL (0 ms). `prefetch_stream_url` publishes a per-key `Event`; `wait_for_prefetch` waits on it (up to 2 s) instead of starting a second resolve.
- A freshly resolved URL is not handed to mpv until `wait_for_stream_url_ready` returns. Symptom without it: mpv opens the URL before the CDN edge accepts the session token and fails or stalls. The probe is a 1-byte Range GET, 3 tries, 0.5 s apart; the wait is capped at 1.5 s and proceeds regardless.
- A URL that already sits in the cache is not re-probed unless younger than the warm-up window.
- The two event dicts are capped at 25 entries (oldest dropped); a dropped event just means a caller does not wait.
- After a playback failure on a cached URL, call `re_resolve`: it drops the entry first. Skipping that replays the same dead URL.

## Threading

Every function blocks and belongs in a worker thread. `resolve_stream_url` registers a cancel event with `src/ytdlp.py` unless the caller passes its own; `cancel_all()` aborts it at exit. Probe threads are daemons.
