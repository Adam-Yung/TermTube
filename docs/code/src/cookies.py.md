# src/cookies.py

Extracts the browser's cookies once and shares the resulting `CookieJar`. Decision history: `docs/decisions/cookies-and-auth.md`. Which calls use the jar, and which must not, is in `docs/code/src/ytdlp.py.md` ("Cookie policy").

## Behavior

- `resolve_browser(config)`: `browser: none` (or empty) returns None, meaning unauthenticated. `auto` or unset picks the first entry from `detect_installed_browsers()` (Firefox first on macOS, since it needs no keychain approval). Any other value is used as given.
- `get_cookiejar(config)` extracts on first use and returns the same jar until `invalidate()`. `prewarm(config)` (called after first paint by `MainScreen._prewarm_cookies`) starts one background thread for it when `cookie_prewarm` is on and a browser resolves; otherwise a session that only searches, plays and browses channels never reads it. Only `ytdlp._make_ydl(..., auth=True)` asks for the jar.
- `_narrow` removes every cookie not on `youtube.com` or `google.com` (including subdomains) right after extraction, in place, so the jar's other cookies never stay in memory. Nothing is written to disk.
- `is_auth_failure(exc)` is true when `errors.classify(exc)` is `SignInRequired` (markers live only in `src/errors.py`). `ytdlp._extract_videos` and `fetch_subscribed_channels` call `invalidate()` on such an error and retry once (the feed loop's existing retry; a second pass in the subscription list). The markers come from yt-dlp's known messages, not a recorded failure; widen them if a real sign-in error slips through.
- Extraction is double-checked under `_lock`: concurrent callers block on the first extraction instead of each reading the browser database. A cold profile takes 5-15 s, so callers run in worker threads, never the UI thread.
- Failure (browser missing, profile locked, keychain denied) returns None and logs at debug level. The next call retries, because nothing is cached on failure.
- `http.cookiejar.CookieJar` has an internal lock, so one jar is safe across threads.

## Limits

- The jar is attached only by `ytdlp._make_ydl`. mpv gets cookies through `Config.browser_cookie_args()`, which is separate.
- A mid-session account switch in the browser is not noticed until an auth failure or a restart.
