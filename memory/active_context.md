# Active Context

## Status: COMPLETED — Jun 18 2026

## Session: Full install/uninstall pipeline audit + perf test sync

### Summary of Changes

**Install Pipeline Fixes:**
1. `bootstrap.py`: Removed system PATH fallback from `is_tool_installed()` — bundled binaries are always downloaded fresh, never skipped because Homebrew/system versions exist
2. `bootstrap.py`: Dynamic macOS version detection for mpv release asset naming (was hardcoding `macos-15`, now correctly uses actual system version e.g. `macos-26`)
3. `bootstrap.py`: Added `filter="data"` to `tarfile.extractall()` calls (suppresses Python 3.14 deprecation warning)
4. `setup.sh`: Fixed exit code 1 bug — bare `return` in `install_shortcut()` propagated `[[ ]]` failure under `set -e`; now uses explicit `return 0`
5. `main.py`: Fixed `_run_tests()` looking for `tests/` instead of `src/tests/` after directory restructuring

**Test Sync (matching today's performance optimizations):**
6. `test_mpv_ipc.py`: Updated IPC test to expect single batched `sendall` (matching persistent socket optimization)
7. `test_updater.py`: Rewrote `TestCheckForUpdateNotification` to match new one-shot notification file API
8. `conftest.py`: Added `_cache=None` reset in `temp_history` fixture (isolates tests from in-memory cache)

**Windows Fixes:**
9. `setup.ps1`: Removed stale `-Sync`/`-Deps` parameter documentation
10. `setup.ps1`: Fixed desktop shortcut to use absolute path to `termtube.cmd`

### Verification
- Full uninstall/reinstall cycle: clean
- All 4 binaries download and execute correctly (yt-dlp, deno, ffmpeg, mpv)
- `versions.json` written with correct platform (macos-aarch64)
- `setup.sh` exits 0 with "Setup complete!" banner
- 235 tests pass, 1 skipped (snapshot placeholder)
- Update pipeline correctly queries GitHub API and skips for dev installs

### Known Gaps (not blocking, for future work)
- No tests for `innertube.py`, `library.py`, `bootstrap.py`
- Today's 13-commit perf sprint has behavioral changes with no test coverage
- Snapshot tests are placeholder-only
- mpv `--version` hangs in non-TTY context (works fine in actual app usage via IPC)
