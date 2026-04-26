# TermTube — Concerns, Bugs & Performance Issues

Audit date: 2026-04-26. All line numbers reference the current `main` branch.

---

## CRITICAL — Broken Features

### 1. Home Feed Suppression is 100% Non-Functional
**Files:** `src/cache.py`, `src/tui/widgets/detail_panel.py:117–118`, `src/tui/screens/main_screen.py:329–331, 530–531`

Three cache methods are referenced but do not exist anywhere in `cache.py`:

| Called | Where | Status |
|--------|-------|--------|
| `cache.register_focus(vid)` | `detail_panel.py:118` | Method missing — guarded by `hasattr`, silently does nothing |
| `cache.suppress_video(vid)` | `main_screen.py:531` | Method missing — guarded by `hasattr`, silently does nothing |
| `cache.is_suppressed(vid)` | `main_screen.py:329` | Method missing — `getattr(cache, "is_suppressed", lambda x: False)` always returns False |

The feature is fully wired up in the UI (focus counting, audio-play suppression, filter in `_stream_feed`) but the backend never records or reads any suppression state. Watched videos are never hidden from the home feed.

**Fix:** Implement `register_focus(vid)`, `suppress_video(vid)`, and `is_suppressed(vid)` in `cache.py`, backed by a JSON file (e.g. `~/.cache/termtube/suppressed.json`).

---

## HIGH — Performance / CPU

### 2. Spinner Timer Fires at 10 Hz Even When Idle
**File:** `src/tui/screens/main_screen.py:49`

```python
self.set_interval(0.1, self._animate_spinner)
```

`_animate_spinner` runs 10 times per second for the entire lifetime of the app. In `IDLE` state it calls `status_widget.update("")` on every tick — that's 10 unnecessary Textual DOM updates + re-renders per second even when the app is doing nothing. This is almost certainly the #1 contributor to idle CPU usage.

**Fix:**
```python
def _animate_spinner(self) -> None:
    if self._state == "IDLE":
        return   # skip the update entirely when nothing is happening
    ...
```

Or use a lower base interval (e.g. 0.5 s) and only animate when `_state == "LOADING"`.

### 3. Audio IPC Poll Opens 3 Separate Socket Connections Per Tick
**File:** `src/tui/screens/main_screen.py:592–600`

```python
def _poll_audio_ipc(self) -> None:
    pos    = get_ipc_property("time-pos", ...)   # open sock → send → recv → close
    dur    = get_ipc_property("duration", ...)   # open sock → send → recv → close
    paused = get_ipc_property("pause", ...)      # open sock → send → recv → close
```

Each `get_ipc_property` call (`player.py:100–105`) creates a new `socket.socket`, connects, sends, receives, and closes. With a 0.5 s poll interval, that is **6 Unix socket lifecycles per second** during audio playback.

**Fix:** Batch all three into one `send_ipc_command` that uses `get_property_string` for all three properties, or hold the socket open and use mpv's `observe_property` subscription instead of polling.

### 4. Double Enrichment of Initial Batch
**File:** `src/tui/screens/main_screen.py:303–308, 420–430`

`enrich_in_background` is called twice for the same first 20 videos:
1. At the end of `_stream_view` (line 303–308) when streaming completes.
2. Again in `on_video_list_panel_batch_revealed` (line 420–430) when the initial batch is revealed from the buffer.

Since `_reveal_entry` runs during streaming (within the first `BATCH_SIZE=20` entries), the initial batch is already "revealed" before streaming finishes, so the `BatchRevealed` message fires first, but then `_stream_view` also calls `enrich_in_background` on completion. The two enrichments run concurrently for the same IDs.

**Fix:** Remove the `enrich_in_background` call from `_stream_view` and rely solely on `BatchRevealed` to trigger enrichment.

### 5. `update_entry_by_id` is O(n) on Both Buffer and DOM
**File:** `src/tui/widgets/video_list.py:354–368`

```python
for i, buf in enumerate(self._buffer):  # O(n) buffer scan
    if buf.get("id") == vid_id: ...
for item in lv._nodes:                  # O(n) DOM scan
    if isinstance(item, VideoListItem) and item.entry.get("id") == vid_id: ...
```

Called for every enriched video. With 20 concurrent enrichments on a buffer of 50+ items, this adds up. A dict lookup by video ID would be O(1).

**Fix:** Keep a `_buffer_index: dict[str, int]` mapping video ID → buffer position, updated in `append_entry`.

### 6. Clock Timer Always Running (Unnecessary When App is Backgrounded)
**File:** `src/tui/screens/main_screen.py:47`

```python
self.set_interval(1.0, self._update_clock)
```

`_update_clock` fires every second and calls `self.query_one("#header-clock", Static).update(...)`. Minor compared to the spinner but still a constant 1 Hz DOM update for the entire app lifetime.

---

## HIGH — Correctness Bugs

### 7. `_background_refresh` Uses an Unmanaged Raw Thread
**File:** `src/tui/screens/main_screen.py:346–347`

```python
t = threading.Thread(target=self._background_refresh, args=(...), daemon=True)
t.start()
```

This thread is not controlled by Textual's `@work` system. It:
- Is not cancelled when the user switches tabs or quits
- Runs `cache.clear_feed()` + `cache.put_feed()` concurrently with `_stream_view`'s `cache.put_video()` calls — no locking on cache file writes
- Exceptions are silently swallowed (bare `except Exception: pass` on line 366)

**Fix:** Promote to a `@work(thread=True)` method so Textual can manage its lifecycle.

### 8. No Atomic Cache Writes — Risk of Corruption
**File:** `src/cache.py:48, 97`

```python
path.write_text(json.dumps(entry, ensure_ascii=False))   # put_video
path.write_text(json.dumps({"_cached_at": ..., "ids": ids}))  # put_feed
```

`Path.write_text` is not atomic. If the process is killed or crashes mid-write, the file is left in a truncated/corrupt state. On next read, `json.JSONDecodeError` is silently caught and `None` is returned — the cache entry is lost and a full re-fetch is triggered.

**Fix:** Write to a `.tmp` file then use `os.replace()` for an atomic swap.

### 9. `enrich_in_background` Can Fire Without Audio Worker Cleanup on mpv Error
**File:** `src/tui/screens/main_screen.py:522–573`

`_launch_audio_worker` has a `try/finally` that only cleans up the temp input.conf file. If `subprocess.Popen` raises `FileNotFoundError` (mpv missing) or `PermissionError`, the exception propagates through Textual's `@work` framework. The UI is left in a broken state:
- `_audio_poll_timer` still runs (set at line 498, never cancelled)
- ActionBar stays in "Now Playing" mode
- `_audio_entry` remains set

**Fix:** Wrap `subprocess.Popen` in a try/except and call `self.app.call_from_thread(self._stop_audio)` on failure.

### 10. `enrich_in_background` Double-Triggers Can Race on Cache Writes
**File:** `src/ytdlp.py` (enrich), `src/cache.py:41–49`

Multiple enrichment threads calling `cache.put_video(entry)` for the same video IDs concurrently can interleave their `path.write_text(...)` calls. Since there's no lock, one thread's partial write can be overwritten by another. The `_active_procs_lock` guards process registration but not cache I/O.

---

## MEDIUM — Code Quality & Correctness

### 11. Duplicate Utility Functions in Two Files
**Files:** `src/tui/widgets/video_list.py:24–70`, `src/tui/widgets/detail_panel.py:22–65`

`_fmt_duration`, `_fmt_views`, and `_fmt_age` are defined identically in both files. Any fix must be applied twice.

**Fix:** Move to `src/tui/utils.py` and import from both.

### 12. `lv._nodes` Private Textual API Used in 4 Places
**File:** `src/tui/widgets/video_list.py:209, 361, 378, 383`

```python
item = lv._nodes[lv.index]
for item in lv._nodes:
if lv._nodes:
nodes = lv._nodes
```

`_nodes` is a private attribute of Textual's `ListView`. It is not part of the public API and has broken in Textual minor version updates before. The public equivalent is iterating `lv.children` or using `lv.query(VideoListItem)`.

### 13. Double `import re` in `ytdlp.py`
**File:** `src/ytdlp.py:14, 83–84`

```python
import re           # line 14 (top-level)
...
import re as _re   # line 83 (module body, outside any function)
```

Both imports coexist. The `_re` alias is used for the `_VIDEO_ID_RE` pattern. The top-level `import re` is unused.

### 14. Stale AI-Generated Comment in Production Code
**File:** `src/tui/screens/main_screen.py:189`

```python
# ... (Rest of MainScreen methods remain exactly the same)
```

This is a copy-paste artifact from AI-assisted development. It has no meaning in the actual file and should be deleted.

### 15. `_play_vlc` Does Not Pass Cookies
**File:** `src/player.py:292–298`

VLC playback doesn't receive the `cookie_args` argument. Any video requiring authentication (age-restricted, members-only, home feed) will fail silently when played via VLC.

### 16. `_play_vlc` Ignores Return Code
**File:** `src/player.py:298`

```python
subprocess.run(cmd)
```

No return code check. VLC errors are dropped silently.

### 17. History `add()` Does Full Read-Modify-Write Every Time
**File:** `src/history.py:26–40`

Every `history.add()` call:
1. Reads and JSON-parses the full 500-entry history file
2. Filters, inserts, truncates
3. JSON-serializes and writes the full file

For a 500-entry file this is a ~100 KB read + parse + serialize + write on every watched video. For audio, this runs inside `_launch_audio_worker` after playback ends. Not a hot path, but still avoidable with an append-only design.

### 18. `library.find_local` Scans All `.info.json` Files on Every Call
**File:** `src/library.py:72–88`

Reads and JSON-parses every `.info.json` sidecar in the library directories to find one video ID. For a library with hundreds of videos, this is expensive. No result is cached.

### 19. `library._scan_dir` Has O(n²) Deduplication
**File:** `src/library.py:55–65`

When an audio file matches a video already in `entries`, it iterates through all entries to find and update it:

```python
for e in entries:      # O(n) scan for every audio file
    if e.get("id") == vid:
```

For large libraries, this is quadratic. A `dict` keyed by video ID would be O(1).

### 20. `import datetime` Inside Hot Function Body
**Files:** `src/tui/widgets/detail_panel.py:47`, `src/tui/widgets/video_list.py:52`

`_fmt_age` is called on every list item render. Python caches module imports so no performance issue, but the pattern is incorrect style and confusing.

### 21. Lazy Imports Inside `@work` Worker Bodies
**File:** `src/tui/screens/main_screen.py:229, 267, 274, 304, 370, 385, 422`

`import src.ytdlp as ytdlp`, `from src import history`, `from src import library`, etc. appear inside worker function bodies. These are consistent (Python caches them), but scattered across the file makes the dependency graph hard to read. Should be top-level.

---

## MEDIUM — Resource Management

### 22. Thumbnail Cache Never Pruned
**File:** `src/cache.py:116–120`

`Cache.clear_all()` deletes feed JSONs and video metadata JSONs, but never touches `THUMB_DIR`. Thumbnail `.jpg` files accumulate indefinitely under `~/.cache/termtube/thumbs/`. A user who browses extensively for months will accumulate gigabytes.

**Fix:** Add a `prune_thumbnails(max_age_days=30)` method and call it on startup.

### 23. Video JSON Cache Has No Size Limit or Eviction
**File:** `src/cache.py`

`put_video` writes one JSON file per video, TTL is 86400 s (24 h), but there's no eviction of old files beyond TTL checks on read. Files stay on disk forever unless `clear_all()` is called. A heavy user will accumulate thousands of files.

**Fix:** Add LRU eviction or a periodic sweep that deletes JSONs older than `N * TTL`.

### 24. `_ensure_dirs()` Called at Module Import Time
**File:** `src/cache.py:18`

```python
_ensure_dirs()  # called at module scope
```

Importing `cache` immediately creates `~/.cache/termtube/{thumbs,videos}/` on disk as a side effect. This is surprising and breaks tests that import cache without wanting filesystem side effects.

**Fix:** Call `_ensure_dirs()` lazily inside `Cache.__init__` or on first write.

---

## LOW — Security & Hardcoding

### 25. IPC Sockets in `/tmp` Are World-Accessible
**Files:** `src/player.py:39`, `src/tui/screens/main_screen.py:91`

```python
IPC_SOCKET  = "/tmp/termtube-mpv.sock"
_AUDIO_SOCKET = "/tmp/termtube-mpv-audio.sock"
```

Any other user on the system can connect to these sockets and send mpv commands (seek, pause, quit, loadfile with arbitrary URLs). On macOS the risk is low (single-user machines) but the sockets should be created in a user-private temp directory.

**Fix:** Use `tempfile.mkdtemp()` at startup and place sockets inside the private directory.

### 26. Magic Strings for Feed Keys and Tab IDs
**Files:** Many

`"home"`, `"subscriptions"`, `"search"`, `"playlist:"`, `"__playlist__"` are compared as raw strings in at least 12 places. A typo is a silent bug.

**Fix:** Define an `enum.StrEnum` for feed keys and playlist prefixes.

### 27. Search Cache Key Uses MD5
**File:** `src/ytdlp.py:242`

```python
cache_key = "search_" + hashlib.md5(query.lower().strip().encode()).hexdigest()[:10]
```

MD5 is deprecated for anything security-adjacent. Use `hashlib.sha256` (also faster on M1 via hardware SHA instructions). Minor, but easy fix.

---

## Summary Table

| # | Severity | Category | File(s) | Status |
|---|----------|----------|---------|--------|
| 1 | Critical | Broken feature | `cache.py`, `detail_panel.py`, `main_screen.py` | ✅ Fixed |
| 2 | High | CPU / idle perf | `main_screen.py:49` | ✅ Fixed |
| 3 | High | CPU / audio perf | `main_screen.py:592–600` | ✅ Fixed |
| 4 | High | Redundant work | `main_screen.py:303–430` | ✅ Fixed |
| 5 | High | CPU / enrichment | `video_list.py:354–368` | ✅ Fixed |
| 6 | Medium | CPU / idle | `main_screen.py:47` | Open |
| 7 | High | Thread safety | `main_screen.py:346–347` | ✅ Fixed |
| 8 | High | Data integrity | `cache.py:48, 97` | ✅ Fixed |
| 9 | High | UI state bug | `main_screen.py:522–573` | ✅ Fixed |
| 10 | High | Race condition | `ytdlp.py`, `cache.py` | ✅ Fixed |
| 11 | Medium | Duplication | `video_list.py`, `detail_panel.py` | Open |
| 12 | Medium | Fragile API | `video_list.py:209, 361, 378, 383` | ✅ Fixed |
| 13 | Low | Dead import | `ytdlp.py:14, 83` | ✅ Fixed |
| 14 | Low | Stale comment | `main_screen.py:189` | ✅ Fixed |
| 15 | Medium | Auth bug | `player.py:292–298` | Open |
| 16 | Low | Silent error | `player.py:298` | Open |
| 17 | Low | I/O perf | `history.py:26–40` | Open |
| 18 | Medium | I/O perf | `library.py:72–88` | Open |
| 19 | Medium | Algorithmic | `library.py:55–65` | Open |
| 20 | Low | Style | `detail_panel.py:47`, `video_list.py:52` | Open |
| 21 | Low | Style | `main_screen.py` (many) | Open |
| 22 | Medium | Disk leak | `cache.py` | ✅ Fixed (`clear_all` + `prune_old_thumbnails`) |
| 23 | Medium | Disk leak | `cache.py` | Open |
| 24 | Low | Side effect | `cache.py:18` | Open |
| 25 | Low | Security | `player.py:39`, `main_screen.py:91` | Open |
| 26 | Low | Maintainability | Codebase-wide | Open |
| 27 | Low | Style | `ytdlp.py:242` | Open |
