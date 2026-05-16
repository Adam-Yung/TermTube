# Active Context

Status: COMPLETED May 2026
Task: Fix Windows install-path architecture so $AppDir and the data dir
(mpv binary + cache + history) don't overlap.

## Root cause
The previous setup put $AppDir = `%LOCALAPPDATA%\TermTube` AND the bundled
mpv install path AND the cache dir all under the same root. Three bugs
followed from that:

1. **mpv vanished on reinstall** — `Install-MpvCli` wrote to
   `%LOCALAPPDATA%\TermTube\mpv\mpv.exe`, then `Install-Files` did a
   `Remove-PathSafe $AppDir` (real dir → recurse-delete) which wiped the
   mpv binary it had just installed.
2. **Sync mode polluted the user's source repo** — `$AppDir` was a junction
   pointing at the repo, so writes to `%LOCALAPPDATA%\TermTube\cache\`
   resolved through the junction into `<repo>\cache\`.
3. **Sync mode silently fell back to standard copy** — `Install-MpvCli`
   creating `$AppDir` first meant `Install-Files` had to demolish a
   pre-populated dir, which could leave the install in an inconsistent
   state and `New-Item Junction` would fail.

## Fix — invert convention so paths don't overlap
- `$AppDir   = %LOCALAPPDATA%\Programs\TermTube\` — code, .venv, launcher.
  May be a junction in sync mode.
- `$DataDir  = %LOCALAPPDATA%\TermTube\`         — mpv, cache, history.
  Always a real directory.

These are now disjoint. Sync-mode reinstalls touch only `$AppDir`, leaving
the user's mpv binary and cache untouched. The paths the running app
probes (`%LOCALAPPDATA%\TermTube\mpv\mpv.exe` and the cache dir) are
unchanged, so existing user installs of those keep working.

## Files changed
- `setup.ps1`:
  - `$AppDir` moved under `\Programs\`; new `$DataDir`; new `$LegacyAppDir`
    constant for migration.
  - `Install-MpvCli` writes to `$DataDir\mpv\` instead of hardcoded path.
  - `Install-Files` migrates from the legacy layout: salvages .venv,
    removes legacy code/launcher artifacts, preserves mpv/, cache/, history.
  - Parent dir `%LOCALAPPDATA%\Programs\` ensured before junction creation.
  - `Install-Launcher` no longer copies to a separate `$BinDir`; just puts
    `$AppDir` on user PATH (termtube.cmd lives in $AppDir via Install-Files
    or the junction).
  - `Main()` runs `Install-Files` BEFORE `Install-MpvCli` (defensive).
- `termtube.cmd`: self-locates with `%~dp0`; no hardcoded SCRIPT_DIR.
- `uninstall.ps1`: knows about the new layout; cleans both new $AppDir and
  legacy code artifacts in $LegacyAppDir; preserves data dir unless
  `-Purge`; strips both new and historical PATH entries.

## Earlier work in this session (still in effect)
- mpv.net rejection: `src/player.py::_mpv_exe(headless=True)` only returns
  the TermTube bundled `mpv.exe` or a non-shim PATH `mpv.exe`. Debug log
  added (`logger.debug "mpv probe: ..."`) so future failures show the
  exact LOCALAPPDATA + probed path.
- `_launch_audio_worker`: surfaces a clear error notification when no
  headless mpv is found, instead of silently spawning mpvnet.
- Cookies/auth split: `Config.cookie_args(*, auth_required: bool = False)`.
- Settings OAuth removed (crashed on Textual ≥ 0.68).
- SHA256 requirements caching in both setup.ps1 and setup.sh.

## Tests
- Full pytest suite passes (264 tests, 1 skipped).

## Pending
- Step 7 of HomeScreen v2 (observe_property event reader in player.py)
  remains deferred to a separate PR per existing memory.
