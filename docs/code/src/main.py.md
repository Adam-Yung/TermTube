# src/main.py

Entry point (`termtube` and `python src/main.py`). Order of operations matters and is the reason most code here exists.

## Startup order

1. Put the project root on `sys.path` and prepend the managed deps bin to `PATH` (so `shutil.which` and yt-dlp find our deno, ffmpeg and mpv first). Done at import time, inline, to avoid importing `src.bootstrap`.
2. Parse args. `-h` and `--test` exit before any setup. `add_help=False` because the help screen is custom.
3. `logger.setup` (nothing is written without `--debug`; see [docs/decisions/logging.md](../../decisions/logging.md)).
4. `--version`, `--browser-help`, `--update` exit here, before the dependency check, so a broken install can still update itself.
5. Dependency check, config, `--clear-cache`.
6. `import textual_image.widget` before Textual starts. It probes the terminal for sixel/TGP support and cell size at import; the probe fails once Textual's I/O threads are running, and images then render wrong or not at all.
7. Create the app, register cleanup, `app.run()`.

## Cleanup

`_emergency_cleanup` (atexit and SIGTERM/SIGHUP on Unix) kills everything in `ProcessRegistry`, closes mpv sockets and cancels yt-dlp work. It looks `src.ytdlp` up in `sys.modules` instead of importing it: `yt_dlp` costs about 170 ms to import and used to load on the main thread before the UI started. The module is first imported by the warmup thread in `TermTubeApp.on_mount`; if it never loaded, there is nothing to cancel. Exit paths are listed in [docs/decisions/concurrency.md](../../decisions/concurrency.md). SIGINT is Textual's. Windows has no SIGHUP, so only `atexit` runs there.

## Quirks and limits

- `VERSION` is read at import; a missing file fails startup.
- `--update` exits 0 regardless of whether every update succeeded.
- `--test` runs the whole `src/tests` tree, and writes `test_results_<ts>.log` under the temp dir.
- `_migrate_legacy_windows_paths` moves `history.json` and `playlists.json` from `~/.config/TermTube` to `%APPDATA%\TermTube`; older Windows builds wrote to the wrong place. Safe to delete once no such installs remain.
