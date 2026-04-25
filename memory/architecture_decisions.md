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

## Why stale-while-revalidate for home feed
Cold starts from a fresh yt-dlp fetch can take 3–8 seconds. The home feed is cached to disk. On launch, the cached data renders immediately. A background worker fetches a fresh feed and swaps it in when done. This gives a sub-100ms perceived startup time.

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
