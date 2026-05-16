# Active Context

Status: COMPLETED May 2026
Task: Polish setup.ps1 + fix mpv GUI window leak on Windows audio playback.

## Changes

### setup.ps1
- New helpers: `Refresh-Path` (preserves session-added PATH entries),
  `Test-IsReparsePoint`, `Remove-PathSafe` (deletes junctions safely without
  recursing into the target — was a data-loss bug), `Test-MpvAvailable`
  (locates the standalone CLI mpv only, never matches `mpvnet.exe`).
- `$WinGetPackages` no longer maps `mpv → mpv.net`. mpv.net's window-spawning
  build is unusable for headless audio; `Install-MpvCli` is the only path.
- `Install-Dependency` no longer adds mpv.net's dir to PATH on install
  (since mpv is no longer in the winget map).
- `Find-Python` version-comparison fixed: was
  `major>=3 AND minor>=11` (rejects 4.x); now correctly accepts 3.11+ AND 4+.
  Extracted to `Test-PythonVersion` helper.
- `Setup-Venv` now SHA256-hashes `requirements.txt` and skips pip install when
  unchanged. Hash stored at `<venv>/.requirements.sha256`. Also detects stale
  venvs (broken interpreter) and recreates them.
- `Install-Files` now:
  - Uses `Remove-PathSafe` so a sync-mode reinstall over a previous
    standard install (or vice versa) doesn't recurse into junctions.
  - Stashes `<AppDir>/.venv` aside on standard reinstall and restores it
    afterward — preserves pip cache across re-runs.
  - Falls back gracefully if junction creation fails.

### setup.sh
- Mirrored the SHA256 requirements-hash cache to `setup_venv` so Unix users
  also skip pip install when `requirements.txt` hasn't changed. Uses
  `sha256sum` (Linux) or `shasum -a 256` (macOS).

### src/player.py — mpv window leak fix
- New `_is_real_cli_mpv(path)` predicate that detects mpv.net's `mpv.exe`
  stub (parent dir contains `mpvnet.exe`).
- `_mpv_exe(headless=True)` on Windows now ONLY returns the TermTube
  bundled standalone mpv.exe OR a PATH `mpv.exe` that is not the
  mpv.net shim. Returns `None` otherwise — never silently falls through
  to mpvnet (which opens a GUI window even with `--no-video` /
  `--force-window=no`).

### src/tui/screens/main_screen.py — audio worker hardening
- `_launch_audio_worker` checks for a headless mpv up front. If
  `_mpv_exe(headless=True)` returns None, it logs an error and shows a
  notification telling Windows users to re-run setup.ps1 (which installs
  the standalone CLI mpv). Prevents the silent "audio finished after 3 s
  with no sound" UX seen when mpvnet was selected.

## Why
- User reported mpv GUI window appearing during audio playback on Windows
  despite `--no-video`, `--force-window=no`, `--no-terminal`, and
  `CREATE_NO_WINDOW`. Root cause: `_mpv_exe(headless=True)` was falling
  through to `shutil.which("mpv")` / the mpv.net dir's stub mpv.exe, which
  is a redirect to mpvnet — and mpvnet ALWAYS spawns a GUI regardless of
  flags. Fix is to refuse those binaries when headless audio is requested
  and force users onto the standalone build that setup.ps1 installs.
- Polish items: hash-cache for pip install, junction-safe `Remove-PathSafe`
  (previous code did `Remove-Item -Recurse -Force` on `$AppDir` which
  follows junctions and would wipe the user's source repo on sync→standard
  reinstall), Python version comparison fix, .venv preservation.

## Tests
- Full pytest suite passes (264 tests, 1 skipped).
- Config/cookie tests still pass after no changes there.

## Pending / Not Done
- Step 7 of HomeScreen v2 (observe_property event reader in player.py)
  remains deferred to a separate PR per existing memory.
