# Feeds and paging

Home feed caching, suppression, paging, and fetch performance.

## 2026-04-25 — Stale-while-revalidate for the home feed (DEPRECATED)

**Deprecated.** The 2026-05-03 redesign in [HomeScreen v2 worker topology](concurrency.md#2026-05-03--homescreen-v2-worker-topology) replaced it, as described below.

Original design: a cold start from a fresh yt-dlp fetch takes 3–8 seconds. The home feed is cached to disk. On launch, the cached data renders immediately. A background worker fetches a fresh feed and swaps it in when done. Perceived startup is under 100 ms.

Why it was removed (HomeScreen v2, May 2026): the "fetch a fresh feed in parallel while serving cache" race launched a yt-dlp subprocess on every cache hit, which contributed to the 30 % CPU spike on home open. The cache is now the source of truth for the UI. Refresh happens only on the explicit `R` keybind, on cold start (no cache), or on a 5-second dwell on a feed tab whose cache is older than 60 minutes.

## 2026-04-25 — LRU suppression for the home feed

YouTube's home feed is not strictly chronological, and the same videos reappear across sessions. TermTube tracks videos focused 3+ times or explicitly watched, and excludes them from future home feed renders. The feed feels fresh on every visit.

## 2026-05-06 — Home feed 3-state boot model (SUPERSEDED)

**Superseded by [Paged system architecture](#2026-05-10--paged-system-architecture).**

The old 3-state model (stash → background append → lazy reveal) was replaced by:
1. **Stash = first unseen page.** On exit, the first page the user has not navigated to is saved, backfilled to exactly 20 entries. On next boot it becomes page 1, so content is always fresh.
2. **Batch fetch.** One yt-dlp call fetches 80 entries (4 pages), split into pages of 20 in memory.
3. **Fixed pages.** No infinite scroll. The user navigates with `]`/`[`. Page N+1 must be ready before `]` is allowed (no-op otherwise).

## 2026-05-10 — Paged system architecture

- **20 entries per page, 80 entries per yt-dlp batch.** Balances freshness against API efficiency.
- **Strict 2-worker ceiling.** At most 1 feed fetch worker and 1 metadata worker. Feed fetch is exclusive and never stacked. The metadata worker cancels before starting (session counter + `proc.terminate()`).
- **`]` is a no-op when the next page is not ready.** Rapid presses cannot bog the system. The page indicator shows "loading next…" as feedback.
- **100 ms focus debounce**, down from 200 ms, for snappier metadata. No neighbour prefetch (removed to honour the 2-worker limit).
- **Stash backfill guarantee.** If fewer than 20 unseen entries exist at exit, backfill from earlier pages so the first page is full on boot.
- **Active workers reference counter.** `_active_workers: int` is incremented and decremented around workers. The spinner shows when > 0 and hides at 0, so it matches real activity.
- **Search is paged too.** Up to 50 results split into pages of 20, with the same `[`/`]` navigation.

## 2026-05-10 — Performance and stability hardening

Decisions from the audit:
- **Prefetch runs on the `focus` worker, not `feed_loader`.** The page-fetch thread keeps a single responsibility. `_schedule_prefetch` is dispatched via `call_from_thread` after feed loading completes.
- **30 s read timeout on yt-dlp subprocess stdout.** It uses `select.select()` + `os.read()` on the raw fd for true non-blocking reads. If yt-dlp hangs, the process is killed and the worker unblocks. (The subprocess reader was later removed with the move to the [yt-dlp library](runtime-and-env.md#2026-06-21--yt-dlp-as-a-python-library-instead-of-a-standalone-binary).)
- **`atexit` + `on_unmount` double guard for subprocess cleanup.** `ytdlp.kill_all_active()` runs in both paths to cover SIGINT, SIGTERM and normal exit. The [process registry](concurrency.md#2026-06-17--unified-process-registry-and-structured-shutdown) later layered more paths on top.
- **Download procs registered in `_active_procs`.** `kill_all_active()` now terminates downloads on quit. They were orphaned before.
- **Thumb worker kept separate.** It is a third exclusive thread for thumbnail rendering (better UX through parallelism). It sits outside the "2 worker" budget because it fetches neither pages nor video info.

## 2026-07 — Single fetch with progressive callback

The home feed uses one yt-dlp call for 80 entries. The `on_first_batch` callback fires after 15 entries arrive and displays them at once, while the remaining 65 stream in from the same network session. This removes the duplicate handshake and auth overhead of the prior two-phase approach (two separate `extract_info` calls).

The feed URL changed from `/feed/recommended` to `https://www.youtube.com/`, which matches the user's proven benchmark. Together with IPv4 forcing, `geo_bypass`, `approximate_date` and no-fsync cache writes, cold start to content takes about 2.5–3 s.

## 2026-11-15 — Channel playlists through InnerTube; `sort` dropped from `innertube.fetch_channel_videos`

The Playlists tab is read from `/browse` with continuation paging (up to 80 entries, 1.0 s live) and falls back to yt-dlp when the response is empty or the channel id is unknown. The InnerTube entry carries the same keys the list row and `_activate_entry` use. `fetch_channel_videos` lost its `sort` argument: it was ignored, and a popular-sort selector was not reliable. The channel screen sends non-date sorts to yt-dlp.
