# src/history.py

Local watch history: videos played through this TUI, not the Google account's history. Stored through [store.py](store.py.md) in
`<config dir>/history.json` (version 2), newest first, deduplicated by video id, capped by `config.history_max` (default 500).

## Invariants

- Records are slim: `id, title, uploader, channel_id, duration, thumbnail` (a URL), `view_count, upload_date` (list rows show views and
  age), plus `watched_at, plays, seconds, resume_s, source`. `_slim` drops everything else, so playing a Library row never stores its
  sidecar, description or formats. `seconds` and `resume_s` are kept across replays; nothing writes them yet (Phase 8).
- `add(entry, config)` is called on the UI thread (audio progress) and from the video modal's worker. It updates the in-memory list
  synchronously under the store lock and defers the disk write (debounced, flushed at exit); a failed write is logged and the entry stays in memory.
- `history: false` records nothing and keeps what exists. `remove_many(ids)` (returns copies of the removed records) and `restore(records)` (re-inserts by `watched_at`, skips an id watched again since) are deferred like `add`; `clear()` writes at once.
- The v1 file (a bare list of full entries with `_watched_at`) migrates on first load: slimmed, `plays` 1, then saved as v2.
- `all_entries()` returns a shallow copy: safe to hold, the dicts are shared.
- Entry ids fall back to `webpage_url_basename`; an entry with neither is ignored.
