# TermTube TUI Inspection Report

**Date:** 2026-07-09
**Scope:** Full codebase review — screens, widgets, backend modules, tests, UX flow, theming

**Summary:** 15 Critical, 34 Important, 40 Nice-to-have findings across 4 review areas.

---

## Table of Contents

1. [Critical Bugs (Must Fix)](#1-critical-bugs-must-fix)
2. [Important Improvements (Should Fix)](#2-important-improvements-should-fix)
3. [Nice-to-Have Enhancements](#3-nice-to-have-enhancements)
4. [Quick Wins (Low Effort, High Impact)](#4-quick-wins-low-effort-high-impact)

---

## 1. Critical Bugs (Must Fix)

### C-01: Undefined variable `count` in `fetch_subscribed_channels`

| Field | Value |
|-------|-------|
| File | `src/ytdlp.py:611` |
| Impact | `NameError` at runtime whenever the channel subscription cache misses |
| Fix | Add `count: int = 100` parameter to the function signature |

The function uses `opts['playlistend'] = count` but never declares `count` as a parameter or local variable. Every other similar function (`fetch_page_batch`, `fetch_channel_playlists`) has it as a keyword argument.

---

### C-02: `os._exit(0)` force-exit can corrupt data

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py:2074-2084` |
| Impact | Bypasses all Python cleanup — open files won't flush, atexit handlers skipped |
| Fix | Use a longer timeout (5s), or move stash/cache writes to happen before `app.exit()` is called |

The 2-second `threading.Timer` fires `os._exit(0)` which kills the process hard. If stash or cache is mid-write (atomic rename), data could be lost.

---

### C-03: `proc.wait()` blocks worker thread indefinitely (WatchModal)

| Field | Value |
|-------|-------|
| File | `src/tui/screens/watch_modal.py:215-217` |
| Impact | If mpv hangs, the `video_player` worker group is permanently stuck |
| Fix | Add `timeout=` parameter and a watchdog that kills stale processes |

No timeout on `self._proc.wait()`. Combined with `exclusive=True`, no other video can launch until app restart.

---

### C-04: `proc.communicate()` blocks worker indefinitely (audio)

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py:1413-1418` |
| Impact | If mpv's stderr pipe never closes, audio worker hangs forever |
| Fix | Use `proc.communicate(timeout=300)` with a try/except `TimeoutExpired` |

Same issue as C-03 but for audio playback.

---

### C-05: Instance attribute `_buffering_since` created outside `__init__`

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/action_bar.py:260, 365` |
| Impact | Fragile — `_refresh_player()` uses `getattr` fallback; masks logic errors |
| Fix | Initialize `self._buffering_since: float = 0.0` in `__init__` |

---

### C-06: Instance attribute `_resize_timer` created outside `__init__`

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/detail_panel.py:225-228` |
| Impact | Race condition if `on_resize` fires before first assignment |
| Fix | Declare `self._resize_timer: Timer | None = None` in `__init__` |

---

### C-07: 17 bare `except Exception: pass` blocks in widgets

| Field | Value |
|-------|-------|
| Files | `video_list.py`, `action_bar.py`, `detail_panel.py`, `thumbnail_widget.py` |
| Impact | Real bugs (rendering errors, data issues) are silently swallowed |
| Fix | At minimum add `logger.debug(...)` inside handlers; narrow to specific exceptions |

Key offenders: `detail_panel.py:272` (entire `update_channel_entry`), `video_list.py:95` (theme read failure).

---

### C-08: Lazy `import time` inside hot path

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/action_bar.py:252, 364` |
| Impact | Unnecessary dict lookup on every progress poll (~2/sec) |
| Fix | Move `import time` to top of file |

---

### C-09: Test coverage: `innertube.py` has zero tests

| Field | Value |
|-------|-------|
| File | `src/innertube.py` |
| Impact | YouTube changes payloads frequently; breakage has no safety net |
| Fix | Add unit tests with fixture payloads |

---

### C-10: Test coverage: `library.py` has zero tests

| Field | Value |
|-------|-------|
| File | `src/library.py` |
| Impact | Disk scan, path resolution, format filtering all untested |
| Fix | Add unit tests for `all_entries()`, edge cases (missing dirs, permissions) |

---

### C-11: Test coverage: `bootstrap.py` has zero tests

| Field | Value |
|-------|-------|
| File | `src/bootstrap.py` |
| Impact | A failure here bricks the app for new users |
| Fix | Add tests mocking HTTP responses and verifying install logic |

---

### C-12: README documents non-existent `a` keybinding

| Field | Value |
|-------|-------|
| File | `README.md`, `src/tui/screens/help_screen.py:71` |
| Impact | Users pressing `a` get no response — confusing |
| Fix | Either add an `a` binding for audio download or remove from docs |

---

### C-13: ROADMAP.md missing entirely

| Field | Value |
|-------|-------|
| File | (does not exist) |
| Impact | Violates project's own `CLAUDE.md` documentation rules |
| Fix | Create `ROADMAP.md` tracking planned/in-progress/done features |

---

### C-14: `_fmt_watched` treats `0` as falsy

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/video_list.py:47` |
| Impact | Timestamp `0.0` (epoch) would be treated as "not watched" |
| Fix | Use `if ts is None:` instead of `if not ts:` |

---

### C-15: O(n) linear scan for child lookup in click handlers

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/video_list.py:83-86, 459-461` |
| Impact | Design smell; fragile if page size grows |
| Fix | Store index on the item or use a lookup dict |

---

## 2. Important Improvements (Should Fix)

### I-01: `MainScreen` is a 2085-line god object

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py` |
| Impact | Maintenance nightmare; impossible to unit test in isolation |
| Fix | Extract audio player (~500 lines), thumbnail worker, and feed loader into mixins or separate modules |

---

### I-02: Unrestricted `zipfile.extractall()` — zip-slip vulnerability

| Field | Value |
|-------|-------|
| Files | `src/updater.py:307`, `src/bootstrap.py:199,254,328,384` |
| Impact | Path traversal via crafted archives (low practical risk since targets are temp dirs) |
| Fix | Validate member paths before extraction or use `shutil.unpack_archive` with safeguards |

---

### I-03: Code duplication — yt-dlp options built 4 times

| Field | Value |
|-------|-------|
| File | `src/ytdlp.py` (lines 186-195, 274-283, ~500, ~611) |
| Impact | Easy for copies to drift (caused C-01) |
| Fix | Extract `_flat_fetch_opts(config, count)` helper |

---

### I-04: Thread-safety — mutable cache returned by reference

| Field | Value |
|-------|-------|
| File | `src/library.py:116` |
| Impact | Callers mutating the list corrupt the internal cache |
| Fix | Return `list(entries)` (defensive copy) |

---

### I-05: Download cancellation doesn't kill subprocess

| Field | Value |
|-------|-------|
| File | `src/tui/screens/download_modal.py:29, 192-199` |
| Impact | Pressing Esc closes modal but yt-dlp continues downloading in background |
| Fix | Expose subprocess handle from `ytdlp.download_video_with_progress()` and terminate on cancel |

---

### I-06: Theme color map duplicated 4 times

| Field | Value |
|-------|-------|
| Files | `video_list.py:98-103`, `action_bar.py:103-113, 115-125` |
| Impact | Adding a new theme requires changes in all locations |
| Fix | Extract shared `THEME_COLORS` dict to a common module |

---

### I-07: Hardcoded color literals bypass theming

| Field | Value |
|-------|-------|
| File | `src/tui/widgets/video_list.py:131, 139-146, 164` |
| Impact | Badge colors (`#6b9eff`, `#6bff6b`, `#6699cc`) don't adapt to theme |
| Fix | Use theme-aware color constants |

---

### I-08: No tests for yt-dlp feed fetching pipeline

| Field | Value |
|-------|-------|
| File | `src/ytdlp.py` |
| Impact | Core data pipeline (`fetch_page_batch`, `fetch_search_batch`, `resolve_stream_url`) all untested |
| Fix | Add integration tests with mocked yt-dlp responses |

---

### I-09: TUI has only 4 tests total

| Field | Value |
|-------|-------|
| File | `src/tests/tui/test_navigation.py` |
| Impact | No coverage for: video action modal, download, settings, watch, quality picker, detail panel, action bar |
| Fix | Add snapshot tests and interaction tests for key flows |

---

### I-10: `s` key collision — Stop audio vs. Subscribe

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py` |
| Impact | `s` stops audio (clearing queue) when playing, opens browser otherwise — confusing dual-purpose |
| Fix | Use a less-destructive stop key, or add confirmation for queue clear |

---

### I-11: `l` key collision — Listen vs. Seek

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py` |
| Impact | Same key does completely different things based on audio state |
| Fix | Document more clearly, or use distinct keys for seek |

---

### I-12: No visual loading feedback for "Listen" action

| Field | Value |
|-------|-------|
| File | `src/tui/screens/main_screen.py:1234-1238` |
| Impact | 2-5s gap where progress shows 0:00/0:00 with no "Loading..." indicator |
| Fix | Show a "Buffering..." state in action bar while `_play_pending` is True |

---

### I-13: WatchModal discards all mpv stderr

| Field | Value |
|-------|-------|
| File | `src/tui/screens/watch_modal.py:189-193` |
| Impact | Video playback failures show no error message to user |
| Fix | Capture stderr like audio path does, surface errors in notification |

---

### I-14: `channel_screen.py` — Unused `_info_proc` attribute

| Field | Value |
|-------|-------|
| File | `src/tui/screens/channel_screen.py:133` |
| Impact | Dead code; `action_go_back()` tries to terminate a never-assigned proc |
| Fix | Remove `_info_proc` and its references |

---

### I-15: Escape on cookie warning permanently suppresses it

| Field | Value |
|-------|-------|
| File | `src/tui/screens/cookie_warning_modal.py:44-45` |
| Impact | Accidental Escape permanently hides the cookie setup prompt |
| Fix | Dismiss with a "skip this session" value, not "never show again" |

---

### I-16: `Config.cache_ttl` method/property name collision

| Field | Value |
|-------|-------|
| File | `src/config.py:195` |
| Impact | `config.cache_ttl` returns a bound method, not the dict; confusing API |
| Fix | Rename to `get_cache_ttl(key)` or similar |

---

### I-17: Thumbnail/focus worker code duplicated between MainScreen and ChannelScreen

| Field | Value |
|-------|-------|
| Files | `main_screen.py`, `channel_screen.py` |
| Impact | ~120 lines copy-pasted; maintenance burden |
| Fix | Extract a `FocusWorkerMixin` or shared utility module |

---

### I-18: `settings_modal.py` — No error handling on `config.save()`

| Field | Value |
|-------|-------|
| File | `src/tui/screens/settings_modal.py:168-169` |
| Impact | Disk full or permission error crashes the modal |
| Fix | Wrap in try/except with user notification |

---

### I-19: SponsorBlock undocumented in README

| Field | Value |
|-------|-------|
| File | `README.md` |
| Impact | Users don't know the feature exists |
| Fix | Add a SponsorBlock section to README |

---

### I-20: Channel navigation (`c` key) undocumented

| Field | Value |
|-------|-------|
| File | `README.md` |
| Impact | Key feature with no discoverability |
| Fix | Add to keyboard reference |

---

## 3. Nice-to-Have Enhancements

### UX Improvements

| # | Finding | File | Suggestion |
|---|---------|------|------------|
| N-01 | No search history or suggestions | `search_modal.py` | Store last N queries, pre-fill on reopen |
| N-02 | No volume control keybinding | `main_screen.py` | Add `+`/`-` for mpv volume IPC |
| N-03 | No repeat/shuffle for audio queue | `main_screen.py` | Add queue shuffle/loop modes |
| N-04 | Footer only shows 5 bindings | `main_screen.py` | Add a "press ? for all keys" hint |
| N-05 | History/Library empty states are terse | `main_screen.py` | Add guidance text like Playlists does |
| N-06 | No file size estimate before download | `download_modal.py` | Show estimated size from format info |
| N-07 | Title truncation at fixed 68 chars | `video_list.py:149-150` | Use responsive width from `self.size.width` |
| N-08 | Description truncation at 500 chars | `detail_panel.py:195-196` | Panel is scrollable — show full description |
| N-09 | PageIndicator has no keyboard interaction | `page_indicator.py:63-73` | Add focus support and arrow key bindings |
| N-10 | `0-9` percent seek keys fire with no audio | `main_screen.py` | Guard with `if not self._audio_playing: return` |

### Code Quality

| # | Finding | File | Suggestion |
|---|---------|------|------------|
| N-11 | `_WAVE_SPEED` constant unused | `action_bar.py:15` | Remove or reference it |
| N-12 | `history.py` `_save()` lacks `fsync` | `history.py:40-53` | Add `os.fsync(fd)` before close for consistency |
| N-13 | Unbounded stream cache stale entries | `ytdlp.py:733` | Add periodic pruning of expired entries |
| N-14 | `cache.py` creates directories at import time | `cache.py:37` | Move to lazy init on first Cache instantiation |
| N-15 | No `__init__.py` in widgets directory | `src/tui/widgets/` | Add for clean public API surface |
| N-16 | `ProcessRegistry.get()` not thread-safe (singleton) | `plat.py:283` | Add a lock or use module-level instance |
| N-17 | Config lacks input validation on user YAML | `config.py:80` | Validate types/keys on load |
| N-18 | `updater.py` reads entire zip into memory | `updater.py:303-304` | Stream in chunks like bootstrap.py does |

### Theming / CSS

| # | Finding | File | Suggestion |
|---|---------|------|------------|
| N-19 | Empty CSS rule `#video-channel { }` | `theme.tcss:1073` | Remove dead rule |
| N-20 | Duplicate `AppHeader #header-status` block | `theme.tcss:35-39, 938-943` | Merge into single definition |
| N-21 | 140 lines of theme variants could be DRY | `theme.tcss:793-934` | Use CSS variables or generation |
| N-22 | `ActionBar` inline `DEFAULT_CSS` duplicates TCSS | `action_bar.py:48-67` | Remove inline CSS, rely on external TCSS |
| N-23 | Emoji characters in badges have variable width | `video_list.py:133` | Replace `📺` with consistent-width Unicode |

### Documentation

| # | Finding | Suggestion |
|---|---------|------------|
| N-24 | Help screen references "TermTube.yaml" not "config.yaml" | Fix filename in help text |
| N-25 | No man page or `--help` docs for CLI flags | Add `--help` output documentation |
| N-26 | `memory/` directory should exist per CLAUDE.md | Already created in this session |
| N-27 | Snapshot tests are a placeholder (`pass`) | `test_visual.py` — implement actual visual baselines |

### Testing

| # | Finding | Suggestion |
|---|---------|------------|
| N-28 | `src/logger.py` — zero tests | Add tests for TUI sink, file-only mode |
| N-29 | `src/deps.py` — only tested indirectly | Add direct tests for dependency validation |
| N-30 | `src/main.py` — no CLI argument parsing tests | Add tests for `--debug`, `--update`, etc. |

---

## 4. Quick Wins (Low Effort, High Impact)

These can each be fixed in under 15 minutes and have disproportionate impact:

| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| Q-01 | Add `count: int = 100` param to `fetch_subscribed_channels` | 1 line | Fixes runtime crash |
| Q-02 | Move `import time` to top of `action_bar.py` | 1 line | Eliminates hot-path overhead |
| Q-03 | Init `_buffering_since = 0.0` and `_resize_timer = None` in `__init__` | 2 lines | Eliminates fragile getattr patterns |
| Q-04 | Change `if not ts:` to `if ts is None:` in `_fmt_watched` | 1 line | Correct epoch handling |
| Q-05 | Remove empty `#video-channel { }` from theme.tcss | 1 line | Dead code cleanup |
| Q-06 | Remove unused `_WAVE_SPEED` constant | 1 line | Dead code cleanup |
| Q-07 | Remove unused `_info_proc` from channel_screen.py | 3 lines | Dead code cleanup |
| Q-08 | Add `logger.debug` to bare except blocks | ~30 lines | Dramatically improves debuggability |
| Q-09 | Extract `_flat_fetch_opts(config, count)` in ytdlp.py | ~15 lines | Prevents future drift bugs |
| Q-10 | Add "Buffering..." text in action bar when `_play_pending` | ~5 lines | Users see feedback immediately |
| Q-11 | Fix README `a` key documentation | 1 line | Eliminates user confusion |
| Q-12 | Add `timeout=300` to `proc.communicate()` | 1 line | Prevents permanent thread hang |

---

## Architecture Observations

### Strengths
- Clean dependency graph with no circular imports
- Proper async/thread patterns (workers for I/O, `call_from_thread` for UI)
- Atomic file writes throughout (tmp + fsync + rename)
- Layered exit handling (on_unmount + atexit + signal handlers)
- Good caching strategy (stash for instant boot, disk for warm, network for fresh)

### Weaknesses
- `MainScreen` is a god object that should be decomposed
- Error propagation is inconsistent (return None vs. silent swallow vs. log)
- No TypedDict or dataclass for video entries — everything is `dict`
- Widget theming relies on hardcoded color literals instead of CSS variables
- Test coverage is heavily concentrated on unit-level (serialization, formatting) with almost no integration or TUI tests

---

## Recommended Priority Order

1. **Fix C-01** (undefined `count`) — immediate runtime crash
2. **Fix Q-01 through Q-12** — all quick wins in one session
3. **Address I-05** (download cancel) — user-visible broken behavior
4. **Address I-12** (buffering feedback) — perceived responsiveness
5. **Address C-03/C-04** (infinite block) — reliability
6. **Create ROADMAP.md** (C-13) — project hygiene
7. **Add tests for innertube/library/bootstrap** — confidence for future changes
8. **Decompose MainScreen** (I-01) — long-term maintainability

---

*This report was generated by automated code review agents. Line numbers are approximate and may have shifted due to recent edits.*
