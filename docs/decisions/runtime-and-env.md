# Runtime and environment

Python environment, yt-dlp packaging, bundled dependencies, update strategy and setup scripts.

## 2026-04-25 — venv instead of conda/mamba

TermTube uses Python's built-in `venv` only. conda/mamba were removed. They need a separate toolchain (Miniforge/Anaconda) that most users lack, add solver complexity, and confuse environment activation. `venv` ships with Python 3.3+ and works the same everywhere. Portability wins over convenience.

## 2026-05-12 — Tool update strategy: GitHub nightly yt-dlp and Deno

TermTube manages its own tool update cadence. It uses no OS scheduler (no cron, launchd or Task Scheduler).

Why the GitHub nightly binary instead of apt/brew/winget for yt-dlp:
- Ubuntu apt stable ships yt-dlp about a year behind. It broke on the Nov 2025 JS runtime requirement.
- yt-dlp recommends the nightly channel for regular users.
- `yt-dlp --update-to nightly` reliably self-updates any GitHub-sourced binary.
- The `yt-dlp/yt-dlp-nightly-builds` build receives daily extractor fixes.

Why Deno is a required dependency:
- Since yt-dlp 2025.11.12, full YouTube support needs a JS runtime (`yt-dlp-ejs`).
- yt-dlp docs recommend Deno. It self-updates via `deno upgrade`.

`LAST_VERSION` update notifications:
- It stores the yt-dlp version string recorded after each successful update.
- On TUI launch, `check_for_update_notification()` runs `yt-dlp --version` in a background worker thread and compares. On a difference it shows a Textual `notify()` toast with old → new version.

`--update` CLI flag:
- It runs `run_all_updates(verbose=True)` synchronously, with no TUI and full stdout output.
- It forces the update regardless of `LAST_UPDATED` staleness.
- It exits 0 on full success and 1 on any failure.
- `main.py` handles it before `app.run()`, after logger setup.

The 2026-06-21 entry [yt-dlp as a Python library](#2026-06-21--yt-dlp-as-a-python-library-instead-of-a-standalone-binary) later replaced the standalone yt-dlp binary with a pip package.

## 2026-05-16 — setup.ps1 uses `Remove-PathSafe`, not `Remove-Item -Recurse -Force`

`Remove-Item -Recurse -Force` on a Windows directory junction follows the link and deletes the target's contents. In sync mode, `$AppDir` (`%LOCALAPPDATA%\TermTube`) is a junction to the user's source repo, so `Remove-Item -Recurse -Force $AppDir` would wipe the repo.

`Remove-PathSafe` checks the `ReparsePoint` attribute. For junctions and symlinks it calls `[System.IO.Directory]::Delete($Path, recursive=$false)`, which removes only the link. For real directories it does the standard recursive delete. Switching from sync to standard mode, or back, is safe.

## 2026-05-16 — setup.ps1 and setup.sh SHA256-hash requirements.txt

Pip's resolver dominates `setup_venv`, often 30–60 s even when nothing changes. Both scripts hash `requirements.txt` with SHA256 and store the digest at `<venv>/.requirements.sha256`. If the file is unchanged, the whole pip step is skipped. Any whitespace or version pin change invalidates the hash. No state lives in the user's home dir. Everything sits under `<venv>` and goes away with it.

## 2026-06 — Error-driven updates (redesign of the update strategy)

This redesign changed the 2026-05-12 [update strategy](#2026-05-12--tool-update-strategy-github-nightly-yt-dlp-and-deno).

- The sentinel file system (UPDATING, LAST_UPDATED, LAST_ATTEMPT) is removed.
- There are no background updates, no timers and no on-exit hooks.
- Updates trigger only when something is broken:
  - Empty feed: prompt a cookie refresh first, then a yt-dlp update if the feed is still empty.
  - Extraction errors, pattern-matched in the exception handler: prompt a yt-dlp update.
- `update_ytdlp()` runs `yt-dlp --update-to nightly` and records the new version.
- `termtube --update` stays for manual full tool updates.

## 2026-06-21 — yt-dlp as a Python library instead of a standalone binary

The bundled `yt-dlp_macos` was a PyInstaller "onefile" binary. On every call it extracted about 35 MB of Python and dependencies into `/tmp/_MEIxxxxxx`. macOS XProtect scanned those fresh files each time (the temp dir changes), adding 10–15 s per call. It was the largest bottleneck in the app: every feed fetch, search, URL resolution and download paid it.

Solution: install `yt-dlp` and `yt-dlp-ejs` as pip packages in the app's venv and use `yt_dlp.YoutubeDL` directly, with no subprocess. This:
- removes the extraction penalty (0 ms instead of 10–15 s);
- removes platform-specific subprocess code (Unix `select()` pipe reader, Windows threaded reader, `CREATE_NO_WINDOW` flags, binary name branching);
- gives one code path across macOS, Linux and Windows;
- allows explicit Deno discovery via `js_runtimes: {'deno': {'path': ...}}` instead of a PATH search.

Dependencies:
- `yt-dlp` (pip): core library.
- `yt-dlp-ejs` (pip): YouTube JS challenge solver scripts. The standalone binary bundled them. The pip package does not.
- `deno` (binary, `bootstrap.py`): JS runtime that runs the yt-dlp-ejs challenges.
- `ffmpeg` (binary, `bootstrap.py`): format merging for downloads. yt-dlp calls it internally.

Thread safety: `YoutubeDL` is not thread-safe. Each concurrent operation creates its own instance, as each worker thread used to spawn its own subprocess.

## 2026-11-15 — Keep `yt_dlp` off the main thread; keep-alive InnerTube transport

`main.py` imported `src.ytdlp` on the main thread only to call `cancel_all` at exit, adding about 170 ms before the UI started (319 to 347 ms against 134 to 157 ms for app import alone). It now consults `sys.modules`. The planned lazy imports inside `ytdlp.py`, `streams.py` and `downloads.py` were skipped: the warmup worker already imports them off the main thread, so they would add edits at many `yt_dlp.` sites for no first-paint gain. `innertube._post_json` moved from `urllib.request.urlopen` to a per-thread `http.client.HTTPSConnection` with a single retry for a stale reused connection; certificate verification is unchanged.

## 2026-11-15 — Row `TypedDict`s, annotations only

Rows stay plain dicts (they come from JSON, yt-dlp and the disk cache, and are mutated with `setdefault` all over). `src/entries.py` names their shapes for readers and editors and a fixture test keeps the parsers inside the declared keys. A runtime schema or dataclass was rejected: it would cost conversions at every boundary for no behaviour the UI needs.

## 2026-11-15 — `ruff` gates commits; not installed by the agent

`ruff.toml` (line length 120, rules `E,F,I,UP`) and a `ruff check .` step in `scripts/verify.sh`; `ruff>=0.8` in `requirements-dev.txt`. The owner approved installing it, but PyPI could not be reached from this network (connection reset), so its safety status could not be read and the hard rule in `AGENTS.md` (fail closed) applied: no `pip install` was run. The gate uses `.venv/bin/ruff`, else the `ruff` already on `PATH` (0.8.1, installed outside this repo). Linting found one real bug from the earlier refactor (an import removed from `watch_modal.py` that `_stop` still used), and the first run also sorted imports and removed unused ones across the tree.

## 2026-11-16 — Dev and app environments kept apart by a script

The installed app is a copy in `~/.local/share/TermTube` with its own venv; the checkout has `.venv`. They were never symlinked, but the checkout's venv was a copy of the app's (its `pyvenv.cfg` records the app path), and a bare `pip` in the owner's shell resolved to the app venv, so `ruff` was installed there. `scripts/dev-setup.sh` now checks the separation and installs only through `.venv/bin/python -m pip`; `scripts/verify.sh` refuses to run against a venv that is not the checkout's. Rejected: making `./termtube` use the app venv or the reverse (they must stay independent so a dev change cannot break the installed app).
