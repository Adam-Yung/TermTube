# Todo

Master record of the 2026-11-17 audit work. Source of items: [plans/2026-11-17-ux-and-performance-audit-PLAN.md](plans/2026-11-17-ux-and-performance-audit-PLAN.md)
(item ids like B4 refer to it). Present state: [status.md](status.md). Work happens on branch `audit-impl`; each phase is one subagent run, every
commit passes `scripts/verify.sh`, the GitHub pipeline runs at each milestone.

Owner answers (2026-11-17): keys `f m M D J K u Q` accepted; Library and Playlists become one tab with a left rail; search suggestions on by
default with an opt-out setting; deletes remove files outright after one confirmation (no trash); cookie prewarm accepted as a setting;
YouTube history is read-only; the Subscriptions tab stays as it is (channel list, Enter opens the channel); order is by ease of verification; new
dependencies approved in principle, but none is planned (own fuzzy scorer, no `send2trash`).

Legend: `[ ]` to do, `[~]` in progress, `[x]` done (commit short hash), `[-]` dropped (reason).

## Phase 0. Measure and verify the unknowns
- [x] P0.1 Resolve the ten appendix items of the plan; record results in `docs/decisions/` and tick the plan's appendix (154466d)
- [x] P0.2 Startup stage timings in `--debug` (A4.6) and a timing note in `docs/guides/startup-debugging.md` (44a81cb)

## Phase 1. Bugs and privacy quick set
- [x] P1.1 Home extension window (B1.1) and test (5fe9c57)
- [x] P1.2 Local lists use real paging (A6) (2b9f1d1)
- [x] P1.3 Playlist `create()` no longer overwrites; stopgap for bare-id rows (B5.1) (2686aa0)
- [x] P1.4 SponsorBlock hash-prefix endpoint (A1.2) (e09299d)
- [x] P1.5 Thumbnail unverified-TLS fallback opt-in, byte cap (A1.1) (4816456)
- [x] P1.6 Temp/IPC dir 0700 and ownership check (A1.7) (de0061f)
- [x] P1.7 Download template guard (A1.3) (54e5d35)
- [x] P1.8 SponsorBlock has no unverified-TLS fallback (3c6d6f9)
- [x] P1.9 Untrusted IPC dir: one plain line, exit 1 (84b3577)

## Phase 2. Shared foundation, History  (milestone 1: pipeline)
- [x] P2.1 `src/store.py` JsonStore (C4); history and playlists use it, search history and channel bookmarks will (4aaf971)
- [x] P2.2 Slim history v2 + migration, write off the UI thread, `history: off`, `--clear-history` (C2, A4.2, A1.5) (7963f50)
- [x] P2.3 List tools in the shared list engine: filter `f`, mark `m`/`M`, context `D`, undo `u` (B7); own fuzzy scorer (5459cda)
- [x] P2.4 History: delete, filter, day groups, settings for cap (B4.1-3, B4.6) (5459cda; the cap setting `history_max` came with P2.2)
- [x] P2.5 Keymap, help, action bar, `keybindings.md` for all new keys; keymap/help/doc consistency test (5459cda)

## Phase 3. Search
- [x] P2.6 Windows: skip the POSIX mode assertion in test_store (pipeline fix) (702fe11)
- [x] P3.0 A running Home load no longer lands in the next tab (session guard on every loader push) (0154870)
- [x] P3.1 Search stack with page and cursor restore (B3.1) (4b8be39)
- [x] P3.2 Persistent search history in the modal (B3.2) (ea91c0c)
- [x] P3.3 Suggestions as you type, on by default, opt-out setting (B3.3) (0b8647c)
- [x] P3.4 Type/sort filters, more than 50 results (B3.4, B3.5) (4cb79a9)
- [x] P3.5 Search modal debounce tests made deterministic (Windows runner flake) (ed5fe0a)

## Phase 4. Library index and delete  (milestone 2: pipeline)
- [x] P4.1 Library index with incremental refresh (C3, A4.3) (81c6c46)
- [x] P4.2 `library.safe_delete`, delete with confirmation, multi-select (A1.4, B5.5) (81c6c46)
- [x] P4.3 Thumbnail and info caching for downloaded items, pin on download, missing-file handling (B5.4) (81c6c46)

## Phase 5. Playlists v2 and Library fusion
- [x] P5.1 Playlist v2 data model and migration (C1) (20816bd)
- [x] P5.2 Playlist management: rename, delete, reorder, move/copy, multi-add, play/enqueue all (B5.1) (20816bd)
- [x] P5.3 One Library tab with left rail: downloads, videos, audio, playlists (B5.3a) (a30fe7e)
- [x] P5.4 Search within Library/playlists, token syntax (B5.2) (a30fe7e)

## Phase 6. YouTube history and account feeds  (milestone 3: pipeline)
- [x] P6.1 Cookie policy extended for the history feed (A1.6) (5fc79b9)
- [x] P6.2 History `Local | YouTube` sub-tab, read-only, import to local (B4) (a0d73f4)
- [x] P6.3 Watch Later through the History source switch (`Y`); Liked has no yt-dlp shortcut (Phase 0), so it is not offered (B1.8) (8fb189c)

## Phase 7. Channel and Home paging
- [x] P7.1 Channel continuations, Shorts/Live tabs, sort, description, back stack (B2.1-2.3, 2.5, 2.9, 2.10)
- [x] P7.2 Channel playlist opens as a list, enqueue all, local channel bookmarks (B2.6-2.8)
- [x] P7.3 Home paging: live iterator or window fix, prefetch earlier, progress text, stale-while-revalidate, hidden-count toggle (B1.2-1.6) (5aca658 cursor, prefetch, progress; 928c5a8 revalidate; `Z` toggle in the commit that adds `show_played`; the live generator is `[verify live]`)

## Phase 8. Settings, auth, polish  (milestone 4: pipeline)
- [x] P8.1 Settings sections, reload from disk, page size setting (A3) (settings search with `/` is not done: one screen of about 26 rows) (f0ddbc2, 291dca1 via merge)
- [x] P8.2 Cookie prewarm setting, refresh account, sign-in vs extraction error split (A2) (a2e8bb2)
- [x] P8.3 Typed source errors, retry/backoff, rate-limit message (A5) (2a5b7e1)
- [x] P8.4 Resume position, watch count, queue view (B4.4, B4.5, B6) (9c61cab via merge)
- [x] P8.5 Help screen and keymap consistency test (B6) (consistency test landed in P2.5; keymap, help and keybindings.md checked by it)

## UI audit (2026-11-18)
Part A (modals, menu, Actions panel). Harness: `src/tests/tui/layout_harness.py`; add a `Scenario` to `test_layout_audit.py` for each new screen.
- [x] Harness: every modal at 80x24, 100x30, 120x40, 160x50 and 60x20 (1ea9b37)
- [x] New-playlist and rename prompt centered; one `ModalScreen` align rule and a shared `.dialog` / `.dialog-list` base (1ea9b37)
- [x] Playlist (21 findings), queue (7), video menu (4), download (1) dialogs: hint and list no longer leave the box (1ea9b37)
- [x] `YtdlpUpdateModal` had no styling; help CSS was in two places (1ea9b37)
- [x] Actions panel no longer repeats footer keys (`/`, `r`); grows to its rows; menu and panel built from `keymap.ROW_ACTIONS` (ae09dae)
- [x] Enter menu hides rows that do not apply (missing file, live, already downloaded) (ae09dae)
- [x] Thumbnail area capped at half the detail panel (the Actions panel was below the screen at 30 rows) (ae09dae)
Left for part B (screens, rail, bars):
- [x] Main screen and channel screen scenarios in the harness (header, tabs, rail, list, detail panel, footer) at the four sizes (`test_screen_layout_audit.py`)
- [x] The Library rail takes width from the list: part of the video row is off screen (rail 24, list `9fr`, detail `11fr`)
- [x] Actions panel lists every tool of every tab on the main screen (21 entries, 7 rows at 100x30); show only the current tab's tools and re-render on tab and rail focus change (`panel_hints`)
- [x] At 80x24 the detail panel leaves 2 rows for the video info; decide a minimum size or a compact layout (info keeps 6 rows, thumbnail hides first)
- [x] `WatchModal` is in the harness (mpv launch and poll stubbed); its box fits at all five sizes, no fix needed

## Bug hunt 1: wiring (2026-11-18)
- [x] `ListToolsMixin._removals`, `ListToolsMixin._after_removal`, `ItemActionsMixin._crumbs`: empty defaults another class always overrode; one wrong MRO order away from the Home paging bug. Removed (dcfcadc)
- [x] `FeedLoaderMixin._pending_show` survived a view change; the next view's first background extension jumped a page (78688c0)
- [x] `theme.tcss`: `#list-loading` rules and eight `Scrollbar` rules matched nothing (470fd62)
- [x] Guards: `test_mixin_wiring.py` (MRO overrides with winners, stubs, `self.x` contracts, bindings, message handlers), `test_hook_wiring.py` (spies through the running screens), `test_theme_wiring.py` (selectors and queried ids)
- [ ] Judgment calls: `DownloadModal` swallows a failed `library.finish_download` with `except Exception: pass` (a download that never registers is invisible); `MainScreen.on_unmount` leaves `app.audio.log` pointing at the dead screen

## Bug hunt 2: error paths (2026-11-18)
- [x] Windows CI: channel breadcrumb and layout-audit tests waited on fixed pauses; now bounded state polling (586bc48). The `\\[` in the crumb failure is a single escape in a repr, not a double escape.
- [x] `DownloadModal` swallowed a failed `finish_download`; now logs, drops the Library cache and notifies with the file name. `MainScreen.on_unmount` detaches the audio log (1248337)
- [x] Synchronous `JsonStore.update` re-raised `OSError` into the UI (playlist create/add on a read-only or full disk crashed the app). Now notice once, data kept dirty, retried, never flushed to another path (7dddd68)
- [x] A raw exception text with markup (`[youtube] id: ... [/x]`) crashed the list message; escaped and cut (video_list)
- [x] `--debug` log redaction of URL queries, cookies, tokens, Authorization (`logger.redact`)
- [x] Damaged-file matrix for all five stores (truncated, wrong type, future version, scalar)
- [ ] Not covered (time budget): per-loader injection matrix for every SourceError, race scenarios of item 3, 5000-row paging budget, playlist name collision after strip. Single-writer assumption is documented in `docs/decisions/concurrency.md`; no cross-process lock exists.

## Always
- [x] Remove dead code found along the way; shared code stays shared (no copies of `_load/_save/_lock`)
- [x] Update mirrors, feature docs, `status.md`, decision log in the same commit as the code

## Other (before this audit)
1. **Branch protection** on `main` requiring the six pipeline jobs (owner, in GitHub settings).
2. **Windows by hand**: `termtube` in Windows Terminal for keys, colours and thumbnails.
3. Minor: bump `actions/checkout` and `actions/setup-python` when newer majors exist (Node 20 deprecation).
