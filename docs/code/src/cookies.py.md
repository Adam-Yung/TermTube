# src/cookies.py

Extracts the browser's cookies once and shares the resulting `CookieJar`. Decision history: `docs/decisions/cookies-and-auth.md`. Which calls use the jar, and which must not, is in `docs/code/src/ytdlp.py.md` ("Cookie policy").

## Behavior

- `resolve_browser(config)`: `browser: none` (or empty) returns None, meaning unauthenticated. `auto` or unset picks the first entry from `detect_installed_browsers()` (Firefox first on macOS, since it needs no keychain approval). Any other value is used as given.
- `get_cookiejar(config)` returns the cached jar while it is under `_MAX_AGE_S` (10 min) old. A mid-session account switch in the browser is picked up after at most that long.
- Extraction is double-checked under `_lock`: concurrent callers block on the first extraction instead of each reading the browser database. A cold profile takes 5-15 s, so callers run in worker threads, never the UI thread.
- Failure (browser missing, profile locked, keychain denied) returns None and logs at debug level. The next call retries, because nothing is cached on failure.
- `http.cookiejar.CookieJar` has an internal lock, so one jar is safe across threads.

## Limits

- The jar is attached only by `ytdlp._make_ydl`. mpv gets cookies through `Config.browser_cookie_args()`, which is separate.
- There is no explicit invalidation hook; staleness is time-based only.
