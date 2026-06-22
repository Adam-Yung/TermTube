# Active Context

## Current Task: COMPLETED
Migrated yt-dlp from subprocess-spawned PyInstaller binary to pip-installed Python library.

## What Was Done
- Added `yt-dlp` and `yt-dlp-ejs` to requirements.txt as pip dependencies
- Completely rewrote `src/ytdlp.py` to use `yt_dlp.YoutubeDL` directly (no subprocess)
- Removed `_install_ytdlp()` from bootstrap.py (no more binary download)
- Removed `yt-dlp` from REQUIRED_TOOLS in deps.py
- Updated all callers to remove `on_proc_started` params
- Replaced `kill_all_active()` with `cancel_all()` (threading.Event based)
- Rewrote updater.py to use pip for updates and library for cookie refresh
- Explicit deno path passed via `js_runtimes` option (no PATH dependence)

## Key Technical Notes
- `YoutubeDL` is NOT thread-safe — each operation creates its own instance
- Cancellation uses `threading.Event` checked in progress hooks
- Feed extraction uses `lazy_playlist=True` for incremental iteration
- deno/ffmpeg/mpv still managed by bootstrap.py as binary deps
