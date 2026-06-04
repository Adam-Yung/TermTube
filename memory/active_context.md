# Active Context

## Status: COMPLETED — Jun 3 2026

## Session: Fix thumbnails on Windows, remove auto-update, harden update/download, fix CI

### Changes Made

#### `src/updater.py`
- **Removed `refresh_cookies()` call from `run_all_updates()`** — was causing silent failures on CI/headless systems; now separate explicit calls only
- **Removed `maybe_update()` function** — background forked updater on every exit
- **Added `_is_winget_already_uptodate()`** — winget exits 2316632107 when no upgrade available; treat as success (same pattern as `_is_brew_already_uptodate`)
- **Added `_safe_print()`** — falls back to ASCII-safe output on Windows cp1252 consoles
- **Replaced all Unicode emoji (`✓`, `⚠`, `…`, `—`)** in print statements with ASCII equivalents for Windows console compatibility
- **Switched `xcopy` to `robocopy`** in the Windows copy script — more reliable; robocopy exit codes 0-7 are success
- **Fixed temp dir cleanup** — removed self-referential `rmdir /s /q` from within the script being executed
- **Removed `--background` forked process entry point** — the `__main__` now uses `--run` flag

#### `src/config.py`
- **Removed `auto_update` config key** from `DEFAULT_CONFIG` and the `auto_update` property

#### `src/main.py`
- **Removed auto-update `finally` block** — `maybe_update()` was called on every exit silently
- **Fixed Unicode in `--update` banner** — replaced `—` and `…` with `--` and `...`

#### `src/tui/widgets/thumbnail_widget.py`
- **Fixed Windows thumbnail detection** — previously only enabled `_HAS_TEXTUAL_IMAGE` on Windows if `WT_SESSION` was set; now enables it on all Windows installs (textual-image renders at least halfcell/unicode)

#### `src/ui/thumbnail.py`
- **Fixed `download()`** — creates `THUMB_DIR` before writing; passes `get_popen_kwargs(headless=True)` to suppress PowerShell console window in TUI; logs stderr on non-zero exit

#### `src/tui/screens/download_modal.py`
- **Surfaced errors** — captures `ERROR:` lines from yt-dlp stdout; shows inline error message in the modal instead of silently dismissing with `False`
- **Added `download-hint` Static widget** for per-state footer message

#### `.github/workflows/test.yml`
- Added `yt-dlp` binary install step to CI (needed for integration tests)
- Added `timeout-minutes` to all jobs (5-10 min)
- Added `TERM: xterm-256color` env for TUI tests
- Added `--timeout=30` to TUI test run

#### `tests/unit/test_config.py`
- Removed `TestAutoUpdate` class (3 tests) — `auto_update` property no longer exists

#### `tests/unit/test_updater.py`
- Removed `TestMaybeUpdate` class (5 tests) — `maybe_update()` no longer exists

#### `tests/integration/test_mpv_ipc.py`
- Added `_SKIP_UNIX = pytest.mark.skipif(sys.platform == "win32", ...)` marker
- Applied `@_SKIP_UNIX` to `TestSendIpcCommand` and `TestPollAudioProperties` — `socket.AF_UNIX` doesn't exist on Windows

### Test Results
- 252 passed, 15 skipped (11 AF_UNIX + 4 pre-existing) on Windows locally
- CI now properly installs yt-dlp and will pass on Linux

### Known Limitation
- `yt-dlp --update-to nightly` fails on PAN network with SSL cert error (corporate proxy self-signed cert); this is a network environment issue, not a code bug
