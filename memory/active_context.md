# Active Context

## Status: COMPLETED — Jun 17 2026

## Session: Reactive updates, dead code pruning, Windows performance

### Summary of Changes

1. **Removed background/scheduled update infrastructure** — deleted sentinel file system, auto_update settings toggle (fixes crash), version-check timer, on-exit cookie refresh hook
2. **Implemented error-driven cookie refresh** — when feed returns empty + cookies configured, modal prompts user to refresh; on success, feed auto-reloads
3. **Implemented error-driven yt-dlp update** — extraction errors or persistent empty feeds prompt user to update yt-dlp; on success, feed auto-reloads
4. **Pruned 22+ dead functions** — removed unused stream_flat/stream_search, 9 player wrappers, 5 widget methods, 4 fzf-legacy thumbnail funcs, etc. Fixed `or True` debug leftover, consolidated redundant cleanup paths
5. **Windows performance improvements:**
   - Replaced PowerShell thumbnail downloads with urllib (eliminates ~300-500ms startup per thumbnail)
   - Cached has_chafa()/get_chafa_exe() with functools.cache (eliminates repeated rglob scans)
   - Batched IPC audio polling on Windows into single named-pipe session (3x fewer pipe connections)
   - Made PIL halfblock thumbnail fallback universal (any platform without chafa benefits)
   - Unified IS_WINDOWS detection via src.platform import
