# Cookies and authentication

Browser cookies, the shared cookie jar, and which yt-dlp calls get authentication. Entries run in date order. Later entries replace parts of earlier ones, so read to the bottom.

## 2026-05-16 — "Generate OAuth2 Token" removed from Settings

The option ran `subprocess.call(["yt-dlp", "--oauth2", "--dump-json", URL], stdout=DEVNULL)` inside `self.app.suspend(_run)`. Two bugs compounded:

1. Stock `yt-dlp` has no `--oauth2` flag. The third-party plugin `yt-dlp-youtube-oauth2` adds it, but the codebase neither checked for it nor told the user to install it. The subprocess errored, output went to `/dev/null`, and nothing persisted to disk. Even on success, the next yt-dlp call had no token.
2. `App.suspend()` on Textual ≥ 0.68 (the project requires ≥ 0.68) is a context manager, not a callable that takes a function. `self.app.suspend(_run)` raised `TypeError` and tore down the modal.

The cookies.txt path covers the authentication need without OAuth2 token persistence. The Authentication section in Settings is removed. Cookie status (path + freshness) shows as a subtitle in the Cookie Browser section. (cookies.txt itself was removed later: see [Pure cookiesfrombrowser](#2026-07--pure-cookiesfrombrowser-rewrite).)

## 2026-06-19 — Browser auto-detection for cookie refresh

The `browser` config key now defaults to `"auto"` instead of `"chrome"`. When it is auto, null or empty, `refresh_cookies()` calls `detect_installed_browsers()` from the new `src/browsers.py` module. (`refresh_cookies()` was removed with cookies.txt: see [Pure cookiesfrombrowser](#2026-07--pure-cookiesfrombrowser-rewrite).)

Detection strategy, with zero dependencies:
- macOS: check for `.app` bundles in /Applications and ~/Applications.
- Windows: check known exe paths under ProgramFiles, ProgramFiles(x86) and LOCALAPPDATA.
- Linux: use `shutil.which()` for known executable names.

Why filesystem checks instead of a library:
- No additional dependency.
- yt-dlp uses the same approach internally (it checks browser data dirs).
- Highly reliable on macOS and Windows, where paths are vendor-standardized.
- Fast: stat calls only, no subprocess.

Interactive CLI selection: when `--refresh-cookies` detects several browsers, it shows a numbered menu on stdin. Non-interactive callers (TUI worker, piped input) get the first detected browser. An explicit `browser` param or config value always overrides detection.

## 2026-06-24 — `_base_opts` vs `_playback_opts` split

`_base_opts()` includes `'extractor_args': {'youtube': {'skip': ['dash', 'hls']}}`, which makes yt-dlp skip DASH/HLS manifest parsing. That suits flat, metadata-only extraction (feed listing, search, channel browsing), where no stream URLs are needed. It saves about 1–2 s per call.

`resolve_stream_url()` and the download functions need DASH format data to pick the right video and audio streams. Sharing `_base_opts` across all calls degraded format resolution: it picked suboptimal formats or failed to find specific quality levels.

Solution: `_playback_opts()` has the same base configuration (cookies, deno path, quiet mode) minus the skip directive. `resolve_stream_url()` also uses the fast path for audio-only formats, where the DASH skip does not affect resolution, and the full path only for video formats.

Measured impact:
- Audio resolution: about 1.9 s (fast path with skip).
- Video resolution: about 2.4 s (full path without skip).
- Feed fetching: unchanged (still `_base_opts` with skip).

## 2026-06-24 — Stream URL pre-resolution on focus

YouTube's InnerTube `/player` API no longer returns `streamingData` without a Proof of Origin token (po_token). Getting the token means running YouTube's JavaScript challenges through Deno + yt-dlp-ejs. A plain HTTP request cannot get playable CDN URLs.

Optimization: the user usually dwells on a video for 1–3 s before pressing play. TermTube pre-resolves the audio stream URL in the background right after the InnerTube metadata fetch completes (about 220 ms). The URL is cached by the time the user acts.

Flow:
1. User focuses a video. The dwell timer fires (100 ms).
2. `_detail_worker` fetches InnerTube metadata (about 220 ms).
3. After metadata, `_prefetch_stream_worker` resolves the audio URL via yt-dlp (about 2 s).
4. The URL is cached in `_stream_cache` (`vid:format → (timestamp, urls)`, 5 h TTL).
5. User presses listen. `get_cached_stream_url()` returns instantly (0 ms).
6. On a cache miss (rare, the user acted very fast), it falls back to an on-demand resolve.

Why audio-only prefetch:
- The audio format (`ba[format_note*=original]/ba`) uses the fast path with skip DASH/HLS (about 1.9 s).
- The video format (`bv+(ba/ba)`) needs full DASH manifest parsing (about 2.4 s).
- Listen is the most common action. Video watch can tolerate 2 s on a cache miss.
- Background network use stays low: one resolve per focused video.

Cache design:
- A simple dict, not disk-cached. CDN URLs are time-limited and not reusable across sessions.
- 20-entry cap with oldest-eviction (a typical session focuses 10–50 videos).
- 5 h TTL (YouTube CDN URLs expire in about 6 h).
- Thread-safe via a Lock, because several workers may read and write.

## 2026-07 — `cookiesfrombrowser` on every call

Before this, TermTube kept a cookies.txt file and refreshed it periodically. That was fragile: the file went stale between sessions, the refresh could fail silently, and the startup refresh added 1–3 s to cold start.

Now every yt-dlp call passes `cookiesfrombrowser` directly. yt-dlp reads the browser's SQLite cookie database inline. If extraction fails (browser not installed, profile locked, etc.), yt-dlp continues without cookies and does not crash. The cost is a small per-call overhead (about 50 ms to read the cookie DB). The gain is guaranteed freshness and zero infrastructure.

## 2026-07 — Pure cookiesfrombrowser (rewrite)

cookies.txt is eliminated. Every yt-dlp call passes `cookiesfrombrowser: (browser, None, None, None)`, which reads the browser's cookie store directly. Cookies are always fresh. All refresh infrastructure is removed: `threading.Event`, the auto-refresh daemon, `CookieWarningModal`, `cookie_args()` and the `cookies_file` config key.

`browser: none` semantics:
- Setting `browser` to `"none"` in config.yaml opts out entirely.
- No `cookiesfrombrowser` option goes to yt-dlp.
- The app runs unauthenticated (generic YouTube results only).
- If browser extraction fails for any reason, yt-dlp continues unauthenticated.

Browser auto-detection: when `browser` is `"auto"` (default), the app calls `detect_installed_browsers()` and picks the first match. For mpv passthrough, `Config.browser_cookie_args()` returns CLI-style args.

## 2026-08-12 — Session-cached cookie extraction

Decision: extract browser cookies once per process lifetime and inject the shared `CookieJar` into all `YoutubeDL` instances.

Why: each `YoutubeDL` instantiation with `cookiesfrombrowser` re-reads the browser's SQLite cookie database (about 200–500 ms). A typical session start makes 3–5 yt-dlp calls, which wastes 1–2 s of I/O.

Implementation: `_get_shared_cookiejar()` extracts once with double-checked locking. `_make_ydl()` injects the jar. `http.cookiejar.CookieJar` is thread-safe (internal RLock). The `cookiesfrombrowser` option is removed from `_base_opts()` and `_playback_opts()`.

## 2026-08-20 — Non-blocking cookies for prefetch

Problem: on a fresh install, the eager prefetch fires at T+2.5 s and immediately blocks on `_jar_lock` while cookie extraction runs (5–15 s). Stream URL resolution then blocks behind Deno's first-run JS compilation (4–8 s). The waits stack serially, for about 30 s before first play.

Fix: `prefetch_stream_url` uses `blocking_cookies=False`, which calls `_get_shared_cookiejar_nonblocking()`. If extraction is still running (the lock is held), it returns None and proceeds without auth. Most public YouTube videos resolve fine unauthenticated.

Regression mitigation: if a video requires auth, the unauthenticated prefetch produces a URL that fails at play time. The retry path now calls `invalidate_cached_stream_url()` before re-resolving. That clears the stale entry, and the retry gets a fresh URL with cookies, which are available by then. Net cost for auth-required videos is about 3 s extra (one retry), against 30 s before.

Why non-blocking instead of skipping cookies entirely: `_get_shared_cookiejar_nonblocking()` returns the jar immediately if extraction already finished. Only the first cold-start prefetch runs without cookies. Later prefetches (focus dwell) always have cookies, because extraction finishes within 5–15 s. The non-blocking path matters only in the race window at app startup.

The 2026-08-21 entry [No cookies for stream resolution or downloads](#2026-08-21--no-cookies-for-stream-resolution-or-downloads) removed the `blocking_cookies` parameter.

## 2026-08-21 — Cookie jar staleness and auto-invalidation

Problem: `_shared_jar` was cached for the whole process lifetime. If the user switched YouTube accounts in the browser mid-session, the jar kept the old account's auth tokens. All later yt-dlp calls failed with 403 or sign-in-required errors, which broke all playback until restart.

Fix, in two layers:
1. **Time-based staleness.** `_get_shared_cookiejar()` checks `_jar_extracted_at` and re-extracts if the jar is older than 10 minutes (`_JAR_MAX_AGE = 600`). This catches an account switch made a while ago.
2. **Error-driven invalidation.** `invalidate_shared_cookiejar()` resets `_shared_jar = None` and `_jar_extracted_at = 0.0`. Any caller that detects auth failures can use it.

Why 10 minutes: YouTube session tokens last hours, but an account switch needs detection within a reasonable window. 10 minutes balances re-extraction overhead (about 50 ms per extraction) against responsiveness to auth changes.

## 2026-08-21 — No cookies for stream resolution or downloads

Problem: passing browser cookies to `resolve_stream_url()` and the download functions made YouTube return a degraded "tv downgraded player" response. It had 5 formats (4 storyboards + 1 combined 360p HLS) instead of 37+ formats with direct HTTPS audio and video streams.

Root cause: the user's new account cookies triggered YouTube's degraded client path. Separately, the default client in yt-dlp 2026.07.04 (ANDROID_VR) produced CDN URLs that returned 403 from non-VR user agents. This is a YouTube-side change tracked in yt-dlp#12482.

Fix: stream resolution and downloads no longer inject the shared cookie jar. They are public operations, and any YouTube video's CDN URL resolves without authentication. Cookies stay in `_make_ydl()` calls only for account-specific operations (home feed, subscriptions, channel browsing).

The yt-dlp minimum is bumped to 2026.08.19. It switches from the broken ANDROID_VR client to VISIONOS, which produces direct HTTPS CDN URLs that work with mpv's `--no-ytdl` mode.

Performance benefit: stream resolution no longer blocks on cookie extraction at startup, and the `blocking_cookies` parameter is removed entirely. Prefetch fires immediately without waiting for the jar lock.
