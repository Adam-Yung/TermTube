# src/store.py

`JsonStore`: the one place that reads and writes the small user JSON files (history, playlists; later search history and channel bookmarks).
It replaces the per-module `_load/_save/_lock/_cache` copies.

## Invariants

- On disk: `{"version": n, "data": ...}`. A file without that envelope (what history and playlists wrote before) reads as version 1.
- The data is loaded once and cached; one `RLock` guards every read and update. Callers use `read(fn)` and `update(fn)` and never keep the
  cached object. `update` is the read-modify-write unit: `fn` mutates the data in place, and a truthy return means "changed, save".
- `path` may be a callable so tests can redirect the file; the store reloads when the resolved path changes.
- Saves go through `plat.atomic_write` (0600, temp file plus `os.replace`). A synchronous `update` re-raises `OSError`; a deferred one
  (`defer=True`) logs it and keeps the data in memory and dirty.
- Deferred saves are debounced by a daemon timer (`_FLUSH_DELAY`, 0.5 s) so the UI thread never waits for the disk. `flush_all` is registered
  with `atexit`, so quitting (including SIGTERM/SIGHUP through `sys.exit`) loses nothing. A hard kill can lose the last half second.
- Unreadable content is never discarded silently: invalid JSON, a wrong top-level type, a version newer than the code, or a failing migration
  copies the file to `<name>.bad` (0600, overwritten each time), logs a warning and starts from the default.
- `migrate(data, from_version)` runs once on load for older versions and the result is saved.

## Limits

Only one process is protected against itself; two TermTube instances writing the same file still last-write-wins.
