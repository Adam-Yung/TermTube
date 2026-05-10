# Active Context

## Current Task: COMPLETED
SponsorBlock integration — full implementation.

## What Was Done
1. **Created `src/sponsorblock.py`** — Segment dataclass, `fetch_segments()` with disk cache at `~/.cache/termtube/sb/{video_id}.json` (24h TTL). Uses stdlib `urllib.request` with 3s timeout. Returns empty list on error/404.
2. **Added config keys** — `sponsorblock.enabled`, `sponsorblock.auto_skip`, `sponsorblock.categories` in `config.py` DEFAULT_CONFIG. Deep-merged on load (same pattern as `cache_ttl`).
3. **ActionBar segment-aware progress bar** — `_text_bar()` renders per-column with green overlay (`#22c55e` filled / `#166534` unfilled) for sponsor segments. `set_segments()`/`clear_segments()` API for the main screen.
4. **WatchModal segment-aware progress** — Replaced Textual `ProgressBar` with Rich-markup `Static` bar (same rendering logic as ActionBar). Fetches segments in `_launch_video()`. Auto-skip in `_poll_mpv()` with `_skipped_indices` guard.
5. **MainScreen audio auto-skip** — Fetches segments in `_launch_audio_worker()` (worker thread). Passes segments to ActionBar via `call_from_thread`. Auto-skip in `_poll_audio_ipc()` with notification.

## Key Design Decisions in This Session
- Segments fetched inside existing worker threads (no new workers needed).
- `_skipped_indices: set[int]` prevents repeated seeks on the same segment during the 500ms poll interval.
- Empty list is cached on 404 to avoid re-querying videos with no segments.
- Falls back to the fast-path (string multiply) bar rendering when no segments are present.
