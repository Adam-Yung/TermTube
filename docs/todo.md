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
- [ ] P3.2 Persistent search history in the modal (B3.2)
- [ ] P3.3 Suggestions as you type, on by default, opt-out setting (B3.3)
- [ ] P3.4 Type/sort filters, more than 50 results (B3.4, B3.5)

## Phase 4. Library index and delete  (milestone 2: pipeline)
- [ ] P4.1 Library index with incremental refresh (C3, A4.3)
- [ ] P4.2 `library.safe_delete`, delete with confirmation, multi-select (A1.4, B5.5)
- [ ] P4.3 Thumbnail and info caching for downloaded items, pin on download, missing-file handling (B5.4)

## Phase 5. Playlists v2 and Library fusion
- [ ] P5.1 Playlist v2 data model and migration (C1)
- [ ] P5.2 Playlist management: rename, delete, reorder, move/copy, multi-add, play/enqueue all (B5.1)
- [ ] P5.3 One Library tab with left rail: downloads, videos, audio, playlists (B5.3a)
- [ ] P5.4 Search within Library/playlists, token syntax (B5.2)

## Phase 6. YouTube history and account feeds  (milestone 3: pipeline)
- [ ] P6.1 Cookie policy extended for the history feed (A1.6)
- [ ] P6.2 History `Local | YouTube` sub-tab, read-only, import to local (B4)
- [ ] P6.3 Watch Later and Liked via the same loader if the extractor shortcuts exist (B1.8)

## Phase 7. Channel and Home paging
- [ ] P7.1 Channel continuations, Shorts/Live tabs, sort, description, back stack (B2.1-2.3, 2.5, 2.9, 2.10)
- [ ] P7.2 Channel playlist opens as a list, enqueue all, local channel bookmarks (B2.6-2.8)
- [ ] P7.3 Home paging: live iterator or window fix, prefetch earlier, progress text, stale-while-revalidate, hidden-count toggle (B1.2-1.6)

## Phase 8. Settings, auth, polish  (milestone 4: pipeline)
- [ ] P8.1 Settings sections, reload from disk, page size setting (A3)
- [ ] P8.2 Cookie prewarm setting, refresh account, sign-in vs extraction error split (A2)
- [ ] P8.3 Typed source errors, retry/backoff, rate-limit message (A5)
- [ ] P8.4 Resume position, watch count, queue view (B4.4, B4.5, B6)
- [ ] P8.5 Help screen and keymap consistency test (B6)

## Always
- [ ] Remove dead code found along the way; shared code stays shared (no copies of `_load/_save/_lock`)
- [ ] Update mirrors, feature docs, `status.md`, decision log in the same commit as the code

## Other (before this audit)
1. **Branch protection** on `main` requiring the six pipeline jobs (owner, in GitHub settings).
2. **Windows by hand**: `termtube` in Windows Terminal for keys, colours and thumbnails.
3. Minor: bump `actions/checkout` and `actions/setup-python` when newer majors exist (Node 20 deprecation).
