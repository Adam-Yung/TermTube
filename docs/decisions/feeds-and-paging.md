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

## 2026-11-15 — Channel first page: RSS, then InnerTube (`src/feeds.py`)

The Subscriptions tab lists channels, so no merged subscription feed was built. The channel page's date-sorted first page goes through `feeds.channel_latest`. A dead-RSS flag (two consecutive 404s, 30 minutes) keeps a blocked network at two wasted requests. Tradeoff: when RSS works it returns 15 entries without durations, where InnerTube returned about 30 with durations. The plan chose RSS first; revisit if the thinner page is noticed. The live fallback check was not run: the request was denied in the session.

## 2026-11-15 — The RSS 404 is not a bad URL

Checked after a question from the owner: the feed URL is the documented form, and `playlist_id=UULF…` also returns nothing here. Public reports from 2026-10-31 describe 404 for every channel, including `UC_x5XG1OV2P6uZZ5FSM9Ttw`, as a YouTube-side outage. The dead flag and InnerTube fallback in `src/feeds.py` stay as built; on a network where RSS works, it is the primary source.

## 2026-11-16 — RSS is down for every probe, on two machines

`scripts/diagnose-rss.py` on the dev Mac and on a second Linux machine (Python 3.12, OpenSSL 3.0) got 404 for all 6 URL forms x 3 channels and all 4 user agents. The 404 page comes from the `YouTube RSS Feeds server` (its own `server` header), while `www.youtube.com` pages return 200 from `ESF`. So the feeds backend answers 404 for every channel; it is not our URL, TLS, a proxy or a user-agent block. Both machines may share one home network, so a different ISP is still untested. Decision unchanged: keep `feeds.channel_latest`; the dead flag costs two requests per 30 minutes and the page recovers by itself when RSS returns. On this evidence the channel page is served by InnerTube (30 entries with durations, about 0.3 to 0.5 s).

## 2026-11-16 — Channel RSS removed; InnerTube is enough

`feeds/videos.xml` answered 404 for every channel, URL form and user agent from two separate networks (the dev Mac and a Linux machine on a different network), and the 404 page came from YouTube's own `YouTube RSS Feeds server`. Public reports describe intermittent 404 windows since December 2025 and a general outage in late October and early November 2026; YouTube has published nothing. `src/feeds.py` (Atom parser, dead flag), its tests, the Atom fixture and `scripts/diagnose-rss.py` were deleted; `ChannelScreen._fetch_videos` calls `innertube.fetch_channel_videos` directly and still falls back to yt-dlp when that returns nothing. InnerTube gives more than RSS did: about 30 entries with durations in 0.2 to 0.5 s, against 15 entries without durations. This supersedes the 2026-11-15 "Channel first page: RSS, then InnerTube" entry. Alternatives considered: the YouTube Data API (needs an API key and a quota, and an account-bound setup this app avoids), PubSubHubbub (push, needs a public callback), yt-dlp (works, 2 to 3 s, already the fallback). If a merged subscription feed is ever built, fetch each channel through InnerTube `/browse` in a bounded pool.

## 2026-11-17 — Audit phase 0: results of the plan's verification list

Offline checks only (code reading, installed yt-dlp 2026.10.26, synthetic data). Numbers are from a dev Mac.

1. **Home extension window: confirmed bug.** `_flat_opts(count)` sets `playlistend=count` and `_extract_videos` drops `skip_ids` after extraction, so the second call (`count=BATCH_FETCH_COUNT`, `skip_ids=seen`) re-reads the same first `count` rows, skips them all and returns nothing. The same holds for the `ytsearch{count}:` fallback. Fix in P1.1: window = `count + len(skip_ids)`.
2. **Local lists are not paged: confirmed.** `_load_simple_list`, the playlist index and playlist view use `_show_one_page`, which stores up to 500 rows as page 1. Fix in P1.2: `add_entries`.
3. **`playlist.create()` overwrites: confirmed.** `PlaylistModal.on_input_submitted` calls it with any typed name, so an existing name is reset to empty and then gets the one video.
4. **History entry size.** `history.add` stores the entry as passed. Rows from feeds are flat (~0.8 KB; 500 entries = 0.4 MB, save 2 ms). Rows played from the Library are the full `.info.json` sidecar with `formats` (synthetic 41 KB each; 500 entries = 20 MB, save 48 ms on the UI thread). Real sidecars are larger. History needs a slim v2 row (P2.2).
5. **YouTube history.** `:ythis` / `:ythistory` exists (`YoutubeHistoryIE`, a `YoutubeFeedsInfoExtractor` with feed name `history`, requires cookies); `:ytwatchlater` redirects to `playlist?list=WL`. What a flat entry carries (timestamp, day section) cannot be read without the network: still open, to be checked by the owner with `yt-dlp --flat-playlist -J :ythis` before P6.2. No Liked shortcut exists in this version.
6. **Sign-in error path.** `_extract_videos` catches `DownloadError`, invalidates the cookie jar and returns an empty list, so a sign-in failure on Home or Subscriptions reaches the empty-feed modal, never the update prompt. The update prompt (`_EXTRACTION_ERRORS`, which includes "sign in") only sees exceptions that escape that catch, where "sign in" would wrongly offer a yt-dlp update. A2 must split the two.
7. **IPC directory.** `os.makedirs(mode=0o700, exist_ok=True)`: the mode is masked by umask, an existing directory is accepted whatever its owner, mode or symlink status, and `$XDG_RUNTIME_DIR` is used unchecked. The log directory is `<tempdir>/TermTube` created with default mode. Fix in P1.6.
8. **Thumbnails.** `download_thumbnail` only checks `len(data) >= 100` and reads without a cap. The pixel path validates with `validate_thumb` (full decode) after the download; the half-block path decodes inside a try block and never deletes a bad file, so it is retried on every view. PIL has webp support here (`features.check("webp")` is true). Fix in P1.5: validate inside `ui.thumbnail.download`.
9. **Keys `f m M D J K u Q`.** None appears in `keymap.py`, any `BINDINGS` list or an `on_key` handler. All free.
10. **Library scan.** 300 synthetic 41 KB sidecars: cold `all_entries` 52 ms, warm (mtime walk only) 0.3 ms. Cold cost is linear in sidecar bytes, so a real library of a few hundred 200 KB sidecars is in the low hundreds of milliseconds, on a worker thread. The index of P4.1 is worth it for size, not for urgency.

## 2026-11-17 — Extraction window includes the skipped ids

`_extract_videos` sets `playlistend` and the `ytsearch<N>:` count to `count + len(skip_ids)`. yt-dlp's window counts rows from the top of the feed, and `skip_ids` are filtered after extraction, so the old window of `count` made every extension batch of Home (and the search fallback) return the rows already shown and so nothing new.

## 2026-11-17 — Local lists page like feeds, but never evict

History, Library and the playlist views load through `add_entries` in `PAGE_SIZE` pages instead of one page of up to 500 rows (`_show_one_page` is gone). They pass `evict=False`: the panel's 30-page memory cap exists for feeds that can be refetched, and a Library of more than 600 items would otherwise lose its far pages for good.

## 2026-11-17 — History v2: slim records, deferred writes

History records keep only what a row and the detail panel show (plus `view_count` and `upload_date`, which the row markup reads, beyond the audit's minimal list) and the counters `plays`, `seconds`, `resume_s`, `source`. `_watched_at` became `watched_at`. `add` updates memory at once and writes after a 0.5 s debounce and at exit, so the UI thread never waits on the disk; a hard kill can lose the last half second. `history: false` stops recording but keeps the file; `--clear-history` erases it.

## 2026-11-17 — Every loader result is session-guarded

A running Home load was not cancelled when the user switched tabs (a thread worker cannot be), so its rows landed in the next tab's list. `_stream_view` now receives the `_feed_session` it started under and keeps it in a thread-local; all loader pushes go through `FeedLoaderMixin._ui`, which re-checks the session on the UI thread. One choke point instead of a session argument on eight loaders.

## 2026-11-17 — Library index keyed by sidecar `(mtime, size)`; deletes are outright and path-checked

The Phase 0 measurement (300 sidecars scan in 52 ms) said the index is about size and robustness, not speed, so it stores only the slim record per sidecar and re-reads a sidecar only when its `(mtime, size)` changes; paths, sizes and the video/audio merge come from the single `os.scandir` walk, so a sidecar can never point a row at another file. `safe_delete` removes files outright (owner answer, no trash, no dependency): every path must be inside a configured root with no symlink and no `..`, and only the media plus same-stem `.info.json`, images and subtitles go. `entry_only` removes the sidecar and keeps the media, because the Library lists sidecars. Thumbnails are normalised to `<stem>.jpg` next to the media (not a separate folder), since that path already survives cache pruning and is deleted with the file group.

## 2026-11-17 — Library delete drops the "entry only" choice

"Entry only" deleted the sidecar and kept the media, so the file vanished from the Library (which lists sidecars) but stayed on disk as an orphan. The choices are now video / audio / both. A row flagged `_missing_file` (sidecar without media) keeps its single "remove entry", which deletes the sidecar.

## 2026-11-18 — Channel page: continuations, Shorts and Live, no popular sort (P7.1)

Videos follow InnerTube continuations with the Home model: the screen keeps the token (`ChannelPager`), fetches the next batch when the user reaches the second-to-last held page, caps the tab at 200 entries and never re-reads an earlier page. Shorts and Live are tabs on the same `fetch_channel_page`; a tab the channel lacks (no tab title in the first `/browse` response) is hidden. Channel info gains `video_count`, `joined` and `tabs` from the response the screen already requests.

Sort: the argument stays removed from InnerTube and non-date sorts go to yt-dlp explicitly. Reading the popular and oldest filter chips means parsing a `chipCloudRenderer` whose continuation tokens come from the first response, and the one earlier attempt at a popular selector was unreliable; yt-dlp's `?sort=p` already works and returns one batch.

**[verify live]** Not recorded against YouTube: the Shorts and Live tab selectors, the `shortsLockupViewModel` parser, the `LIVE` and "N watching" badges, and the "Joined" header text. The fixtures for these are hand-written. A recorded channel response should replace them; until then a layout mismatch shows as an empty tab ("No content found."), never an error.

Also: one `channel_ref.parse` replaces the string splitting of channel URLs. `ChannelScreen._channel_id` resolves an `/@handle` URL once through `innertube.resolve_channel_id` on the worker, so handle channels reach InnerTube too.

## 2026-11-18 — Channel info column: description folded, `i` expands (P7.1)

The description shows its first three lines; `i` expands it. The handoff proposed `a` or Enter, but `a` is audio and Enter is the action menu on the channel page (one key, one action), so the key is `i`. The video count comes from the header text ("442 videos") and the join date from a header text starting "Joined"; both are read from the `/browse` response the screen already requests, with no new request. The join date is **[verify live]**: the current layout may only carry it in the About popup, in which case the stats line shows the video count alone.

## 2026-11-18 — Channel back stack is the screen stack (P7.1)

No second stack: a channel opened from a channel is another `ChannelScreen` pushed on the first, so `Esc` returns to its origin for free. What was missing was context, so each page shows a breadcrumb (`Home › A › B › Videos`) built from a `trail` passed at construction. `c` on the channel page now opens a row that belongs to a different channel (rows in another channel's playlist, once P7.2 lists them); rows with no channel id still count as this channel.

## 2026-11-18 — Channel playlists open inside the channel page (P7.2)

Enter on a playlist row opens its videos in the same list (InnerTube `VL<id>` browse with continuations, yt-dlp when empty); `Esc` returns to the Playlists tab. No new screen: the list, pager, filter and breadcrumb are the channel page's. Bulk keys `P` play all, `E` enqueue all, `S` save as a local playlist. `E` was free (the single-track key is lower-case `e`); `P` and `S` were free. Play all replaces the queue, enqueue all skips known tracks, both through new `AudioController` methods so the queue rules live in one place. Save keeps the channel playlist's name; saving into an existing local playlist of that name only adds the missing ids. **[verify live]**: the playlist page parser and its fixture are hand-written.

## 2026-11-18 — Local channel bookmarks and the Following view (P7.2)

`channels.json` (`JsonStore`) holds `{id, name, avatar, added}`; `B` on the channel page toggles it. The view is `F` on the Subscriptions tab, a drill-down from that tab like a playlist (Backspace returns), so it needs no new tab and works with `browser: none`. The existing Subscriptions behaviour is unchanged, as the owner decided. Keys: `B` and `F` were free; `F` is shift-`f` (filter) only by letter, the filter is not offered on that key. While wiring the back path the playlist drill-down turned out to leave its rows on screen after Backspace (an unchanged `Tabs.active` fires nothing); `action_nav_back` now reloads in that case, for playlists and Following alike.

## 2026-11-18 — Home continues one open listing; hooks were shadowed (P7.3)

Feed extension no longer re-extracts from the top. `src/feed_cursor.py` keeps one lazy flat yt-dlp listing per loaded view, `fetch_page_batch(cursor=)` uses it for the first 80 rows and `_fetch_next_batch` advances it by 80 per extension. A live iterator is safe here because every advance goes through one lock (one thread at a time), `close()` never touches the generator while a `take` runs (the running `take` closes the extractor when it returns), and the cursor's cancel event is registered with `ytdlp.cancel_all`. A failed `take` drops the generator and reopens from the top on the next call, with `skip_ids`, so the old windowed behaviour remains the fallback. When the start was served from the cache the cursor opens at the first extension and skips the held ids once. Applies to Home, History on YouTube and Watch Later; Search keeps its own paging.

Found on the way: `ListNavMixin` defined no-op `_on_last_page_reached` and `_on_past_last_page` and precedes `FeedLoaderMixin` in `MainScreen`, so the loader's hooks never ran in the real app and Home never extended (the tests called `_extend_feed` directly). The no-op defaults are gone; the hosts define `_on_page_shown` and `_on_past_last_page`.

Prefetch moved to the second-to-last held page for feeds (`_on_page_shown`); one extension per session in flight (`_extending_session`), a page request meanwhile only marks the result to show (`_pending_show`). Extension errors used to be swallowed; they now show as `⚠ <typed message>` in the footer, with a hint when the user was waiting.

**[verify live]** The real generator across calls with the extractor left open (the tests use a fake that records opens and reads).
