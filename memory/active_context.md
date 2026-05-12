# Active Context

Status: COMPLETED May 2026
Task: yt-dlp update strategy + Deno dependency + auto-updater

Changes:
- src/updater.py: new module — UPDATING/LAST_UPDATED sentinel, maybe_update() fork, run_all_updates() sync, check_for_update_notification(), get_ytdlp_version(), LAST_VERSION tracking
- src/main.py: --update CLI flag (foreground sync), finally block after app.run() for maybe_update()
- src/deps.py: Deno added as required dep; _print_manual_install shows GitHub/official URLs
- src/platform.py: yt-dlp and Deno install hints updated; nightly-builds URLs
- src/tui/screens/main_screen.py: _check_update_notification() worker + set_timer(0.8) in on_mount
- setup.sh: install_ytdlp_github() downloads nightly; install_deno_official(); Apple Silicon /opt/homebrew path fix
- setup.ps1: Install-YtDlpGitHub() from nightly-builds; Deno in WinGetPackages; deno in required deps
- tests/unit/test_updater.py: comprehensive unit tests for all updater functions
- README.md: prerequisites table updated, Automatic Updates section added
- memory/architecture_decisions.md: tool update strategy documented
