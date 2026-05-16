# Active Context

Status: COMPLETED May 2026
Task: Scope browser-cookie fallback to auth-required pages; remove crashing
OAuth2 Generate option from Settings.

Changes:
- src/config.py: `cookie_args` converted from `@property` to method
  `cookie_args(*, auth_required: bool = False)`. Same priority chain
  (cookies.txt → browser → none) but browser fallback only runs when
  `auth_required=True`. `cookie_source` docstring clarifies it describes
  the auth-required chain.
- src/ytdlp.py: helper `cookie_args(config, *, auth_required=False)` forwards
  to the config method. `stream_flat` got a new `auth_required: bool | None`
  param — defaults to `feed_key in FEED_URLS` (home / subscriptions).
  `fetch_page_batch` got an explicit `auth_required: bool = False` param.
  `fetch_subscribed_channels` pins `auth_required=True`. All other
  call sites (`stream_search`, `fetch_search_batch`, `fetch_full`,
  `fetch_stream_urls`, `download_video_with_progress`,
  `download_audio_with_progress`, `fetch_channel_info`,
  `fetch_channel_playlists`) inherit `auth_required=False`.
- src/tui/screens/main_screen.py: three `fetch_page_batch` call sites
  (in `_load_feed_paged`, `_fetch_more_pages`, `_prefetch_more_pages`)
  pass `auth_required=True` because they serve the Home tab. Audio
  playback (`_launch_audio_worker`) calls
  `config.cookie_args(auth_required=False)`.
- src/tui/screens/watch_modal.py: video playback uses
  `config.cookie_args(auth_required=False)`.
- src/main.py: startup warning now uses `cookie_args(auth_required=True)`
  and wording clarifies non-auth pages still work without cookies.
- src/player.py: docstring updated to reference the new method signature.
- src/tui/screens/settings_modal.py: removed the broken
  "Generate new OAuth2 Token" option, the `auth-list` ListView, and
  `_generate_oauth_token`. Replaced with a read-only Static
  `#s-auth-status` showing cookies.txt path/state, browser fallback
  status, and the resolution rules. Tab cycling list updated.
- tests/unit/test_config.py: TestCookieArgs rewritten — file priority,
  browser fallback ONLY when `auth_required=True`, empty otherwise.
- tests/unit/test_stream_prefetch.py: mocks switched to
  `config.cookie_args.return_value = []` (callable, not attribute).
- tests/integration/test_ytdlp_download.py: `fake_config` mock same fix.

Why:
- Default `browser: chrome` in DEFAULT_CONFIG meant unauthenticated users
  always got `--cookies-from-browser chrome` attached. When Chrome wasn't
  running / cookies couldn't be extracted (Linux keyring lock, wrong
  browser, etc.), yt-dlp errored — breaking pages that don't even need
  auth (search, channels, watch, download). Now only Home / Subs / Subs-
  channels take that risk; everything else falls through to "no cookies"
  as soon as cookies.txt is absent.
- `Settings → Authentication → Generate OAuth2 Token` crashed the app:
  stock yt-dlp has no `--oauth2` flag, AND `App.suspend(callable)` is a
  TypeError on Textual ≥ 0.68 (`suspend()` is a context manager there).
  Removed wholesale.

Tests: 260 passed (unit + integration).
Pushed as commit fix(auth): scope browser-cookie fallback to auth-required pages…
