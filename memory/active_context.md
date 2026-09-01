# Active Context

Last completed: Thumbnail regression fix + pipeline consolidation (ccebfaa).

**Bug fixed:** `_channel_thumb_worker` and `_thumb_worker` in MainScreen shared a single `_thumb_session` counter despite being in independent Textual worker groups. Bumping the counter in one path silently cancelled the other, causing intermittent "no thumbnail" on the main page. Split into `_thumb_session` (video) and `_ch_thumb_session` (channel avatar).

**Consolidation:**
- Extracted `ensure_thumb_jpeg()` and `validate_thumb()` into `thumbnail.py` — replaces 4 duplicated download+validate blocks across workers in main_screen.py and channel_screen.py
- Removed duplicate `_best_thumb_url` from `ytdlp.py` (canonical copy in `thumbnail.py`)
- Removed dead code: `config.thumbnail_cols`/`thumbnail_rows` properties, `cache.has_thumb()`/`thumb_path()`, `thumbnail_cols` help_screen entry
- Net: -90 lines across 9 files, zero test regressions (270 pass)
