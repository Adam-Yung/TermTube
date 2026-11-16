# src/history.py

Local watch history: videos played through this TUI, not the Google account's history. Stored as one JSON list in
`<config dir>/history.json`, newest first, deduplicated by video id, capped at `_MAX_ENTRIES` (500).

## Invariants

- The list is cached in `_cache` after the first read. Every `add()` replaces the cache and rewrites the file, so reads never touch disk
  again. Edits made to the file while the app runs are not seen.
- `_lock` guards both the cache and the write. `add()` is called from worker threads, readers from the UI thread.
- Writes are atomic through `plat.atomic_write` (unique temp file in the same directory, then `os.replace`). A crash mid-write leaves the old file.
- A corrupt or unreadable file loads as empty history, and the next `add()` overwrites it.
- Entries are the video's metadata dict plus `_watched_at` (epoch seconds).
- `all_entries()` returns a shallow copy: the list is safe to hold, the dicts are shared.
