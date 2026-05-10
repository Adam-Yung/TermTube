# Architecture Decisions

## Why venv instead of conda/mamba
Python's built-in `venv` is used exclusively. conda/mamba were removed because they require a separate toolchain (Miniforge/Anaconda) that most users don't have, introduce solver complexity, and create confusion around environment activation. `venv` ships with Python 3.3+ and works identically everywhere. Portability over convenience.

## Why mpv via IPC instead of subprocess blocking
`mpv` is launched with `--input-ipc-server` pointing to a Unix socket (`/tmp/termtube-mpv-audio.sock`). Commands (seek, pause, quit) are sent as JSON over the socket, making all interactions non-blocking. A blocking `subprocess.run(mpv)` would freeze the entire Textual event loop since Textual runs on a single thread for UI updates.

For **video** playback (full-screen), `app.suspend()` is used instead — this yields the terminal completely to mpv and restores the TUI on mpv exit. IPC is only used for background audio.

## Why `app.suspend()` for video, IPC for audio
- Video needs the full terminal; `app.suspend()` hands control over cleanly and restores Textual state on return.
- Audio is headless; the TUI must remain interactive while audio plays, so IPC is the only viable approach.

## Why `@work(thread=True, exclusive=True)` for network calls
Textual's event loop is async but single-threaded for DOM updates. `yt-dlp` calls are synchronous and can block for seconds. Running them in threads via `@work(thread=True)` keeps the UI responsive. `exclusive=True` cancels any in-flight worker of the same type before starting a new one, preventing race conditions when users navigate quickly.

## Why stale-while-revalidate for home feed (DEPRECATED — see HomeScreen v2 below)
~~Cold starts from a fresh yt-dlp fetch can take 3–8 seconds. The home feed is cached to disk. On launch, the cached data renders immediately. A background worker fetches a fresh feed and swaps it in when done. This gives a sub-100ms perceived startup time.~~

The "fetch a fresh feed in parallel while serving cache" race was removed in HomeScreen v2 (May 2026). It launched a yt-dlp subprocess on every cache hit, contributing to the 30 % CPU spike on home open. The cache is now the source of truth for the UI; refresh happens only on the explicit `R` keybind, on cold start (no cache), or on a 5-second dwell on a feed tab whose cache is older than 60 minutes.

## HomeScreen v2 worker topology (May 2026)
The original screen fanned out 3–5 concurrent subprocesses on home open:
- 1 × `yt-dlp stream_flat` (initial feed)
- 2 × `yt-dlp fetch_full` from a `ThreadPoolExecutor(max_workers=2)` triggered eagerly by `BatchRevealed(20 ids)`
- 1 × silent `yt-dlp` background revalidate
- 1 × `chafa --optimize=3 --color-space=din99d` per cursor keystroke (no kill of previous)
Plus `set_interval(600, _scheduled_home_refresh)` and `set_interval(0.5, _poll_audio_ipc)`.

The redesign collapses this to three screen-owned, exclusive workers:
- `feed_loader` — only on cold start, explicit `R`, or stale-cache tab dwell
- `focus` — fires after 200 ms cursor dwell; runs `fetch_full` for the focused video and (best-effort) one neighbour in the cursor's last direction
- `thumb` — fires after 150 ms cursor dwell; checks RAM + disk chafa cache before spawning a chafa subprocess
Each worker stores its `Popen` handle on the screen and `terminate()`s the previous one before dispatching a new request, so `@work(exclusive=True)`'s "swap the Python wrapper" is backed by an actual OS-level cancellation. Session counters guard against late callbacks racing with cancellation.

Chafa flags moved from `--optimize=3 --color-space=din99d` to `--optimize=1` (the perceptual colour-space matrix conversion was the most expensive part and made no visible difference on thumbnails). Output is cached under `~/.cache/termtube/chafa/<vid>_<cols>x<rows>_<fmt>.ansi` so re-rendering at the same panel size is free.

The 10-minute `_scheduled_home_refresh` `set_interval` was deleted outright — it fired regardless of which tab the user was on, contributing to "the spike happened while I wasn't even on home" reports. Freshness is now visible in the list-panel header (`updated 4m ago · R to refresh`), refreshed every 60 s by a single `Static.update`.

DetailPanel became a passive view: the screen calls `update_basic`, `set_thumbnail_loading`, `set_thumbnail_image`, `set_thumbnail_ansi`, `set_thumbnail_placeholder`, `refresh_metadata`. Resize / screen-resume in the panel post a `RerenderRequested` message that the screen handles by re-kicking the thumb worker.

Housekeeping moved out of `App.on_mount` into a 60-second `set_timer` plus an `on_unmount` backstop, so it stops competing with the home feed render at startup.

## Why LRU suppression for home feed
YouTube's home feed is not strictly chronological — the same videos reappear across sessions. TermTube tracks videos that have been focused 3+ times or explicitly watched, and excludes them from future home feed renders. This makes the home feed feel "fresh" on every visit.

## Why `textual-image` + chafa fallback for thumbnails
`textual-image` provides native Sixel (tmux/iTerm2/WezTerm) and Kitty graphics protocol support, which render at full image quality. Terminals that don't support these protocols fall back to `chafa`, which generates ANSI block/Unicode sextant art. This covers effectively all terminal environments.

## Why config lives at `~/.config/TermTube/config.yaml`
XDG-compliant placement. The project root should be clean (no user-specific files committed). Placing config in `~/.config/TermTube/` also means it survives reinstalls and is consistent whether the user runs from the dev dir or the installed copy at `~/.local/share/TermTube/`.

## Why `--sync` creates a directory symlink instead of file-by-file symlinks
`ln -s <orig_dir> <app_dir>` makes the entire install path point to the repo. This means `.venv` created at `APP_DIR/.venv` actually lives inside the repo dir, surviving re-runs of `--sync`. File-by-file symlinks lose the venv on `rm -rf APP_DIR` (which setup.sh does before re-linking).

## Why fzf/gum were deprecated
Both tools require shell subprocess spawning and don't integrate cleanly with Textual's reactive widget model. All UI is now native Textual widgets, enabling proper focus management, async data binding, and consistent theming.

## Why `--debug` makes logging completely silent (not just suppressed)
Without `--debug`, `logger.setup()` sets the logger level above `CRITICAL` and attaches no handlers. Python's logging machinery short-circuits in `Logger.isEnabledFor()` *before* any string formatting happens, so every `logger.debug(...)` call is essentially a single attribute lookup and integer comparison. No file is ever opened, no stderr output, nothing in the in-app debug window. This is both faster (no formatting cost) and more professional (no error noise leaks into a quiet TUI).

## Why nothing is written to stderr — even in `--debug` mode
Textual owns stdout/stderr while the app is running; any stray write corrupts the rendered frame (cursor jumps, ghost characters, breakage of the alt-screen). The original logger had a `StreamHandler(sys.stderr)` for convenience during development, but in practice it produced visible glitches as soon as anything logged from a worker thread. The file handler at `$TMPDIR/TermTube/<ts>.log` plus the in-app Ctrl+D window are sufficient and never collide with the renderer.

## Why `--level` defaults to `ALL` (= DEBUG) rather than `INFO`
`--debug` is opt-in already — if a user reaches for it, they want everything. Defaulting to `INFO` would silently throw away the most useful records (cache hits, yt-dlp commands, mpv launches) the moment someone enables debugging. `--level` exists for the rare case where a noisy run needs to be filtered down to warnings/errors only; making the user pass `--level WARNING` for that is a small cost in exchange for "everything is captured" being the default.

## Why mpv stderr is captured via `PIPE` and drained with `communicate()`
`subprocess.DEVNULL` made silent mpv failures look identical to a finished playback ("Audio finished" toast after 3 seconds with no audio output). To diagnose those, mpv now runs with `--msg-level=all=error` and stderr is captured via `PIPE`. `communicate()` is used (rather than reading stderr after `wait()`) because mpv can fill a 64 KiB pipe buffer with a chain of yt-dlp errors and deadlock waiting for someone to read it. `communicate()` drains stderr concurrently with the wait. The exit code then drives a tri-state branch (success / user-stopped / failure), and only failures bypass history and surface a notification with the first stderr line.

## Why a custom `_TUIHandler` instead of routing logs through `MainScreen._log`
A logging handler is the natural seam for "send every log record somewhere additional." It works for any module that imports `logger` (cache, ytdlp, player, widgets) without requiring those modules to know about Textual. The handler invokes a registered callback (`register_tui_sink`); the callback is responsible for marshalling to the UI thread (`app.call_from_thread`). The `_termtube_skip_tui` record attribute (set by `logger.file_only`) lets `MainScreen._log` write rich-markup directly to the RichLog and still persist a plain version to the file *without* duplicating the line in the TUI.

## Home feed 3-state boot model (May 2026) — SUPERSEDED

**Superseded by the Paged System (May 2026).** See below.

The old 3-state model (stash → background append → lazy reveal) has been replaced by:
1. **Stash = first unseen page**: On exit, the first page the user hasn't navigated to is saved (backfilled to exactly 20 entries). On next boot, this becomes page 1 — always fresh content.
2. **Batch fetch**: A single yt-dlp call fetches 80 entries (4 pages), split into pages of 20 in memory.
3. **Fixed pages**: No infinite scroll. The user navigates with `]`/`[` keys. Page N+1 must be ready before `]` is allowed (no-op otherwise).

## Paged System Architecture (May 2026)

Key design decisions:
- **20 entries per page, 80 entries per yt-dlp batch** — balances freshness with API efficiency.
- **Strict 2-worker ceiling** — at most 1 feed fetch worker + 1 metadata worker. Feed fetch is exclusive (never stacked). Metadata worker uses cancel-before-start (session counter + proc.terminate()).
- **`]` key is a no-op when next page isn't ready** — prevents rapid presses from bogging the system. The page indicator shows "loading next…" as visual feedback.
- **100ms focus debounce** — reduced from 200ms for snappier metadata. No neighbour prefetch (removed to honour the 2-worker limit).
- **Stash backfill guarantee** — if fewer than 20 unseen entries exist at exit, backfill from earlier pages so the user always sees a full first page on boot.
- **Active workers reference counter** — `_active_workers: int` incremented/decremented around workers. Spinner shows when > 0, hides when == 0. Honest to the user.
- **Search is paged too** — up to 50 results split into pages of 20. Same `[`/`]` navigation.

## Performance and Stability Hardening (May 2026)

Key decisions from the audit:
- **Prefetch runs on the `focus` worker, not `feed_loader`** — keeps the page-fetch thread clean (single responsibility). `_schedule_prefetch` is dispatched via `call_from_thread` after feed loading completes.
- **30s read timeout on yt-dlp subprocess stdout** — uses `select.select()` + `os.read()` on raw fd for true non-blocking reads. If yt-dlp hangs, the process is killed and the worker unblocks gracefully.
- **`atexit` + `on_unmount` double-guard for subprocess cleanup** — `ytdlp.kill_all_active()` runs in both paths to handle SIGINT/SIGTERM/normal exit.
- **Download procs registered in `_active_procs`** — ensures `kill_all_active()` terminates downloads on quit (previously they were orphaned).
- **Thumb worker kept separate** — a 3rd exclusive thread for thumbnail rendering (better UX via parallelism), intentionally outside the "2 worker" budget since it's not fetching pages or video info.

## SponsorBlock Integration (May 2026)

Key decisions:
- **Uses the simple `videoID` endpoint, not the privacy-preserving hash prefix** — we already know the full video ID, so the hash-prefix approach adds complexity for no privacy gain (the video was already fetched via yt-dlp).
- **Segments fetched in the existing worker thread** — for audio, fetched inside `_launch_audio_worker` (already `@work(thread=True)`); for video, inside `_launch_video`. No new worker needed.
- **Disk cache at `~/.cache/termtube/sb/{video_id}.json` with 24h TTL** — avoids redundant API calls on re-listen. Empty list cached on 404 (video has no segments) to avoid retrying.
- **Progress bar rendered character-by-character when segments present** — each column maps to a time range; columns overlapping a segment render in green. Normal playback color otherwise. Falls back to the original fast-path string multiplication when no segments exist.
- **Auto-skip uses a `_skipped_indices: set[int]` guard** — prevents the same segment from triggering repeated seeks if the poll fires before mpv finishes seeking past the segment boundary.
- **`urllib.request` (stdlib) instead of `httpx`/`requests`** — zero new dependencies. 3-second timeout so a slow/down API doesn't block playback start noticeably.
- **Configuration is a nested dict (`sponsorblock:` key in config.yaml)** — mirrors the `cache_ttl` pattern. Deep-merged on load so partial user overrides don't clobber other defaults.
