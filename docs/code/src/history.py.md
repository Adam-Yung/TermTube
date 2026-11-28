# src/history.py

Local watch history: videos played through this TUI, not the Google account's history. Stored through [store.py](store.py.md) in
`<config dir>/history.json` (version 2), newest first, deduplicated by video id, capped by `config.history_max` (default 500).

## Invariants

- Records are slim: `id, title, uploader, channel_id, duration, thumbnail` (a URL), `view_count, upload_date` (list rows show views and
  age), plus `watched_at, plays, seconds, resume_s, source`. `slim` drops everything else, so playing a Library row never stores its
  sidecar, description or formats. `seconds` and `resume_s` are kept across replays and written by `record_progress` (see `src/progress.py`).
- `add(entry, config)` is called on the UI thread (audio progress) and from the video modal's worker. It updates the in-memory list
  synchronously under the store lock and defers the disk write (debounced, flushed at exit); a failed write is logged and the entry stays in memory.
- `history: false` records nothing and keeps what exists. `remove_many(ids)` (returns copies of the removed records) and `restore(records)` (re-inserts by `watched_at`, skips an id watched again since) are deferred like `add`; `clear()` writes at once.
- The v1 file (a bare list of full entries with `_watched_at`) migrates on first load: slimmed, `plays` 1, then saved as v2.
- `all_entries()` returns a shallow copy: safe to hold, the dicts are shared.
- Entry ids fall back to `webpage_url_basename`; an entry with neither is ignored.
- Each write is a module function bound with `partial` and run by `JsonStore.update`; its return value both says "save" and carries the result (records removed, rows imported).

`slim(entry, vid, keys=_KEPT)` is public: the Library index reuses it with a longer key list, so a row played from the Library is stored as slim as any other.

`import_entries(entries, config)` copies YouTube history rows into the store: ids already present are skipped (local rows win), new ones become slim records with `source="yt"`, `plays` 0 and `watched_at=None`. `None` is the "unknown time" sentinel: they are appended after every dated row (so `restore`'s sort keeps them last), show under the "Earlier" day header, and are the first to fall off the `history_max` cap.

`record_progress(vid, resume_s=, watched=, duration=)` adds watched seconds to the record and sets where to resume (None clears it); a video without a record (history off, removed meanwhile) is left alone. Deferred like `add`. It runs on whatever thread polls mpv, which is why it goes through the store lock. `duration` fills only an empty field: the record's own `duration` is what the History row's `▶ 2:05 / 10:00` marker divides by. `add` keeps `plays`, `seconds`, `resume_s` and a known `duration` when a video is played again. `flush()` is the quit path's explicit write: `_force_exit` ends with `os._exit`, which skips `atexit`. `ordered(entries, sort)` backs the History `s` chooser: `plays` sorts by plays, then time watched; `time` by time watched; both are stable, so ties stay newest first. `get(vid)` returns a copy of one record.

- `slim` keeps `_local_path` and `_local_type` for a local file id (`local_files.is_local_id`) whose path encodes as UTF-8 (`local_files.encodable`; a surrogate would make every later save raise): history and playlist records of a local file must play it from disk; without the path the id could only be looked up online.
