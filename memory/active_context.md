# Active Context

## Status: COMPLETED — Jun 19 2026

## Session: Browser auto-detection for cookie refresh

### Summary of Changes

1. **New module: `src/browsers.py`** — Zero-dependency browser detection for macOS (app bundle checks), Windows (Program Files exe paths), and Linux (PATH executables). Returns list of installed browsers compatible with yt-dlp's `--cookies-from-browser`.

2. **`src/updater.py`** — `refresh_cookies()` gains a `browser` parameter override and auto-detection logic. When config is set to "auto" (new default), it detects installed browsers and uses the first found. Explicit `browser=` param from the CLI overrides both config and detection.

3. **`src/main.py`** — `--refresh-cookies` now presents an interactive numbered menu when multiple browsers are detected and stdin is a TTY. Single-browser systems auto-select without prompting.

4. **`src/config.py`** — Default `browser` changed from "chrome" to "auto" for new installs. Existing user configs are unaffected (they keep their explicit value).

5. **`src/tui/screens/settings_modal.py`** — Browser list dynamically populated: "Auto-detect" option first, then installed browsers, then non-installed browsers with "(not found)" suffix.

6. **`src/tests/unit/test_browsers.py`** — 16 unit tests covering all three platform detectors, helper functions, and refresh_cookies integration.

### Verification
- 221 unit tests pass (all existing + 16 new)
- No lint errors
