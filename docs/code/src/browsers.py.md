# src/browsers.py

Finds browsers installed on this machine that yt-dlp can read cookies from. `src/cookies.py` uses it when `browser` is `auto`; `src/tui/screens/settings_modal.py` uses the lists and labels for the picker. Decision history: `docs/decisions/cookies-and-auth.md` (2026-06-19).

## Design

Filesystem checks only, no dependency, no subprocess: `.app` bundles in `/Applications` and `~/Applications` (macOS), known exe paths under `ProgramFiles`, `ProgramFiles(x86)` and `LOCALAPPDATA` (Windows), `shutil.which` on known executable names (Linux). This is a stat-only cost and matches how yt-dlp locates browser data.

## Invariants

- Result order is detection priority and `cookies.resolve_browser` takes the first. On macOS the order is Firefox, Brave, Chrome, ...: Firefox needs no keychain approval, Chromium-family browsers prompt for the keychain, Safari's cookie store is sandboxed. Reordering `_MACOS_APP_BUNDLES` changes which browser auto mode picks.
- `YTDLP_SUPPORTED_BROWSERS` lists the names yt-dlp accepts for `cookiesfrombrowser`; a browser missing from the detection tables can still be chosen by name in config.
- `is_auto_browser` treats None, `""` and `"auto"` as auto. `"none"` is handled in `cookies.resolve_browser`, not here.

## Limits

Installed does not mean logged in or readable: a detected browser may have no YouTube session, a locked profile, or a denied keychain prompt. Extraction then fails and the app runs unauthenticated.
