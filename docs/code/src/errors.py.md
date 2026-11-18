# src/errors.py

Typed source errors. `SourceError` (with `message`, `detail`, `retry_after`) has four subclasses: `SignInRequired`, `RateLimited`, `NetworkDown`, `ExtractionFailed`.

## Behavior

- `classify(exc_or_text, status=None)` is the only classifier. Order: rate limit (`HTTP Error 429`, `too many requests`, status 429), sign-in (`sign in`, `login required`, 401/403), network (status 5xx, `urlopen error`, DNS, timeout, reset; or the wrapped exception is a `URLError`/`OSError`), else `ExtractionFailed`. A `SourceError` is returned unchanged.
- `message` is the short text the list shows (`⚠ ` is added by the loader). `SIGN_IN_MESSAGE` is the sign-in text with the Settings shortcut.
- `ytdlp._extract_videos` and `fetch_subscribed_channels` raise these when a fetch really failed; an honestly empty feed still returns `[]`. `innertube._post_json(strict=True)` raises `RateLimited`/`NetworkDown` after one retry (`innertube._sleep`, 1 s, is the injectable pause); `innertube.search` uses it for the first page and `ytdlp.fetch_search_batch` falls back to yt-dlp on it for plain search.
- `FeedLoaderMixin._report_failure` maps them: sign-in, rate limit and network show their message; the yt-dlp update prompt opens only for `ExtractionFailed` on Home.
