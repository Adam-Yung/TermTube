# Audit and plan: UX, performance, and the local data model

Written 2026-11-17 from a read of `AGENTS.md`, `docs/status.md`, the feature docs, the decision logs and the source (not from running the app).
Items marked **[verify]** are inferences from reading code; confirm them before building. Edit freely: strike items, reorder, change calls.

How to read this: Part A is the cross-cutting audit (security, tokens, settings, startup). Part B is per module. Part C is the shared data model
the History, Library and Playlist work depends on. Part D is a suggested order. Part E lists the questions only you can answer.

Rules that bind all of it: `AGENTS.md` (every feature gets tests, mirrors updated, `scripts/verify.sh` green, keys added to `keymap.py` + help +
action bar + `keybindings.md` together, one decision-log entry per call). Nothing here downloads data or models; every new network call is a
metadata request to YouTube through the existing yt-dlp or InnerTube paths.

---

## Part A. Cross-cutting audit

### A1. Security and privacy

What is already good: cookies lazy, narrowed to two domains, in memory only, never sent to InnerTube, streams, downloads or SponsorBlock;
`atomic_write` creates files 0600; per-session IPC socket; subprocess registry kills children on every exit path.

| # | Finding | Why it matters | Proposal |
|---|---|---|---|
| A1.1 | `plat.download_thumbnail` retries with `ssl.CERT_NONE` after any SSL error (`src/plat.py` ~205-250) | Thumbnails are decoded by PIL. A man-in-the-middle can feed crafted image bytes into the decoder, and the downgrade is silent. The code comment calls it acceptable for public images, but the risk is the parser, not the privacy of the image. | Make it opt-in: config `insecure_thumbnails: false`, plus a one-time notice naming the cause ("your network intercepts TLS"). Default behaviour on SSL error: placeholder thumbnail. Also cap bytes read (e.g. 2 MB) and run `Image.verify()` before render (the pipeline has `validate_thumb`; confirm it runs on this path too). **[verify]** |
| A1.2 | SponsorBlock request sends the full video id: `…/skipSegments?videoID=<id>` (`src/sponsorblock.py:164`) | The third party sees every video you play, with your IP. | Use the hash-prefix endpoint (`/api/skipSegments/<sha256(id)[:4]>`) and filter locally by id. Same data, k-anonymity. Document it in `cookies-and-auth.md` as a privacy decision. |
| A1.3 | Download path templates (`video_format`, `audio_format`) are free text passed to yt-dlp `outtmpl` | A template containing `..` or an absolute path escapes `video_dir`. Low risk (the user edits their own config) but it becomes real once Library gets a delete action that trusts paths under those dirs. | Validate on load: strip path separators from the template, or resolve the final path and refuse anything outside the configured dir. Needed before C-section deletes. |
| A1.4 | Library delete (planned, B5) must never follow symlinks or delete outside `video_dir`/`audio_dir` | A sidecar's `_local_path` is derived by scan, but a planted symlink in the download dir would be followed. | One helper `library.safe_delete(path, roots)`: `resolve()` the path, require it to be inside a configured root, refuse symlinks, delete only the file group (media + `.info.json` + thumbnail). Test with symlink and `..` cases. |
| A1.5 | History and playlists are plain JSON in the config dir, 0600 | Fine, but history holds full video dicts (description, formats?) **[verify]** and is never encrypted. | Store slim records (C2). Add `termtube --clear-history`. Add a config switch `history: off` (private mode) that skips `history.add`. |
| A1.6 | The YouTube-history feature (B4) is the third account-bound call | The cookie policy table says exactly two calls carry cookies. | Extend the policy deliberately: a decision entry, the table in `docs/code/src/ytdlp.py.md` and `accounts-and-cookies.md` updated, `auth=True` only for that one URL. Read-only: no write requests to YouTube are made (see B4). |
| A1.7 | IPC sockets and temp files: `/tmp/termtube-<uid>` and `tempfile.gettempdir()/TermTube` | Predictable names in a shared temp dir are a classic symlink/race target on multi-user machines. | Confirm directory is created 0700 and verified to be owned by the user before use; if not, fail closed. **[verify]** |

### A2. Tokens, cookies, auth lifecycle

- **Cookie read cost (5-15 s) lands on the user's first Home load.** Today the read is lazy, which is the right default for privacy, but on the
  common path (browser set, user opens Home) the cost is paid in the foreground.
  Proposal: when `browser` resolves to a real browser, start the cookie read in a background thread right after first paint (not before),
  so Home usually finds a warm jar. Still lazy for `none` and for users who never open Home... but we cannot know that. Make it a setting:
  `cookie_prewarm: true|false`, default true when a browser is configured. Decision-log entry required because it reverses "nothing is read at
  startup".
- **No cookie expiry timer, only renew-on-error.** Switching accounts in the browser is not noticed until an auth error. Proposal: a visible
  "Account: <browser> · signed in / not signed in" line in Settings, and a `Refresh account` action (Settings or `Ctrl+R` on Home) that calls
  `cookies.invalidate()` then reloads. Today the only fix is restarting.
- **Auth failures and empty feeds are indistinguishable to the user.** `_EXTRACTION_ERRORS` includes "sign in" and opens the yt-dlp update
  prompt, which is wrong for a signed-out browser. Split: sign-in error -> "Not signed in in <browser>" modal with Settings shortcut;
  extraction error -> the update prompt. **[verify]** which branch fires today.
- **Token structure for the YouTube history page** is covered in B4. No SAPISIDHASH or InnerTube cookies (owner decision stands).

### A3. Settings

Gaps in the current 4-item Settings modal (theme, quality, thumbnail format, browser):

- Everything else is YAML-only: `video_dir`, `audio_dir`, name templates, cache TTLs, SponsorBlock, `prefetch_video`, page size. Add sections:
  **Playback** (SponsorBlock on/off, categories, auto-skip, prefetch video), **Downloads** (dirs, templates, quality), **Data** (history on/off,
  history cap, cache TTLs, clear cache / clear history), **Account** (browser, refresh account), **Display** (theme, thumbnails, rows per page).
- Show path of config file and a "reload from disk" action (today you must restart after editing YAML).
- Validate and explain on bad values instead of silently falling back (theme, thumbnail format already do this silently).
- Make `PAGE_SIZE = 20` a setting; small terminals want 10, tall ones want 40. It is a module constant in `video_list.py`.
- Settings search (`/` inside Settings) once it exceeds one screen.

### A4. Startup

What exists: yt-dlp warm-up thread, stash of page 1 shown instantly, `reap_orphans`, housekeeping deferred 60 s, lazy yt-dlp work.

| # | Finding | Proposal |
|---|---|---|
| A4.1 | `import yt_dlp` at module top of `ytdlp.py`, `downloads.py`, `streams.py`; `MainScreen` imports them on first use but the warm-up thread imports anyway | Measure `python -X importtime -m src.main`. If yt-dlp still precedes first paint, import inside functions and warm in the thread (the handoff plan already lists this, "cold start" item). |
| A4.2 | `history.add` runs on the UI thread, loads and rewrites the whole JSON (500 full entries) on every first poll of a track (`audio_controller.py:408`, `watch_modal.py:143`) | Slim records (C2) plus write behind a short debounce on a worker. Keeps the UI thread free during playback start. |
| A4.3 | `library.all_entries` walks both trees twice (`_dir_mtime` then `rglob`) and parses every `.info.json` on any change; yt-dlp sidecars are 100 KB to several MB because they hold `formats` | Library index (C3): a slim `library.json`, rescan only changed sidecars. This is the biggest startup/tab-switch cost for a large library. **[verify with a 500-item library]** |
| A4.4 | Home needs cookies (5-15 s cold) then yt-dlp (2-3 s) before fresh entries; the stash hides this for page 1 only | Prewarm (A2); show a per-stage status line ("reading browser session…", "asking YouTube…", "got 15") instead of a bare spinner. |
| A4.5 | Housekeeping scans dirs at 60 s and at exit if not done | Fine. Move the exit-time run to a flag file ("housekeeping due") so quit never waits on pruning. **[verify]** |
| A4.6 | No startup timing log | Add `--debug` stage timings: config load, first paint, first rows, stash shown, jar ready. One table in `docs/guides/startup-debugging.md`. Makes every other change measurable. |

### A5. Error and empty states (affects every tab)

- InnerTube errors become empty results (documented known limit). A user on a flaky network sees "No content found." with no cause or retry.
  Proposal: return a typed result `(entries, error)` or raise a small `SourceError`; the list shows `⚠ Network error · r to retry`. Retry once
  with 1 s backoff inside `_post_json` for 429/5xx; surface 429 as "YouTube is rate limiting this IP".
- A global status line (the spinner exists): show which source answered (`cache`, `innertube`, `yt-dlp`) in debug builds. The handoff plan
  already asks for rung logging; surface it in the debug log pane.
- Offline mode: if all fetches fail fast, the local tabs (History, Library, Playlists) still work. Make sure they never wait on the network
  (Playlist rows currently call `cache.get_video_raw`, which is disk only, good).

### A6. Cross-module consistency

- One **list engine** serves Home, Search, History, Library, Playlists and Channel. New list features (filter, sort, delete, multi-select) go
  into `VideoListPanel` / a mixin once, not per screen. This is the most important structural point of this plan.
- Local tabs (History, Library, Playlist index, Playlist view) are loaded as one page (`_show_one_page`), which breaks paging if a list exceeds
  20 rows. **[verify]** `_load_simple_list` uses `add_page(1, entries)` with all entries; check whether `PAGE_SIZE` is applied. If not, a 500-entry
  history is one giant page and the page indicator is wrong. Use `_show_pages` (`add_entries`) for all local lists.

---

## Part B. Per module

### B1. Main page (Home): fetching and progressive layering

Today: stash (page 1 of last session) shows instantly; then either disk cache (fresh within 1 h) or one yt-dlp flat extraction of up to 80,
the first 15 delivered early; extension calls `fetch_page_batch` again with `skip_ids`.

Problems and proposals:

1. **Extension probably re-fetches the same window [verify].** `_flat_opts(count)` sets `playlistend=count` and `fetch_page_batch` is called
   again with the same `count=80` and `skip_ids`. yt-dlp starts at item 1 each time, so after the first 80 are seen, the second call returns the
   same 80 minus the skip set, i.e. almost nothing. Fix: `playlistend = len(skip_ids) + count` (and keep `skip_ids`), or better, hold a continuation
   token (see 2). Write a test with a fake extractor that records `playlistend`.
2. **Use YouTube's continuation instead of re-extracting.** yt-dlp's lazy playlist iteration already pages with continuation tokens. Keep one
   live generator per tab session (`ydl.extract_info(..., process=False)` then iterate entries lazily) in a worker, advance it N items when the
   user nears the end, close it on view change. This turns "re-extract from the top" (2-3 s each, growing) into a constant-cost next page and
   removes the `skip_ids` hack. Cost: a long-lived worker holding a yt-dlp instance; must be cancelled by `cancel_all`. Needs a design note in
   `docs/decisions/feeds-and-paging.md`.
3. **Progress feedback while paging.** `show_next_page_loading` shows a loading state, but no counts. Proposal: footer reads
   `Page 3 / 4 · loading 40 more…`, then `…81 videos`. Prefetch trigger: fetch when the user reaches the **second-to-last** page, not the last
   (`_on_last_page_reached`), so a reading-speed user never waits.
4. **Layered first paint.** Order today: stash -> cached/fresh. Proposed layers, each replaces only what is below the cursor:
   - L0 stash page (instant, today),
   - L1 first 15 fresh entries (today: placed at page 2+, so the stash page stays stable; keep),
   - L2 remaining 65 fresh entries (today),
   - L3 background top-up to 160 at idle, saved to the id cache so the next launch has a 2-page stash, not 1.
   Stash size becomes a setting (`stash_pages: 1..3`).
5. **Stale-while-revalidate.** When the cache is fresh we never refetch, so Home can be up to 1 h behind. Proposal: when the cache is older than
   10 min, show the cache immediately and revalidate in the background; if new items arrive, show a non-intrusive `↑ 12 new · press r` chip
   rather than reshuffling the list under the cursor.
6. **Suppression ("played videos suppressed") is invisible.** Add `Settings -> Home hides watched` and a count in the footer
   (`18 hidden`) with a key to toggle (e.g. `Z`; **[verify]** key is free).
7. **Subscriptions tab lists channels, not videos.** RSS was dropped; the common user expectation is a subscription video feed. Options:
   (a) yt-dlp `https://www.youtube.com/feed/subscriptions` with cookies (auth call, same policy as Home); (b) per-channel InnerTube fetch
   for the top N channels in parallel (anonymous, bounded pool, cached 10 min). (a) is one call but cookie-bound and 2-3 s; (b) avoids cookies
   but is N requests. Recommend (a) as a sub-view `Subscriptions -> Feed | Channels`, reusing the Home loader (it is already in `FEED_URLS`).
   `cache_ttl.subscriptions` is currently reserved and unused; this gives it a job.
8. **Other account feeds for free** via the same loader and yt-dlp shortcuts: Watch Later (`:ytwatchlater`), Liked (`LL` playlist),
   Recommended (`:ytrec`). Sub-menu in a single "Account" tab group; see B4 for the shape.

### B2. Channel page: better and less limiting

Today: InnerTube `/browse` first page only (~30 newest videos, no continuation), `most viewed` falls back to yt-dlp, playlists up to 80, tabs
Videos / Playlists, sort `s`, reload `r`, back `Esc`.

| # | Limit | Proposal |
|---|---|---|
| B2.1 | Only ~30 videos, no more pages | Follow InnerTube continuations (already done for playlists) with the same prefetch-ahead model as B1. Page cap of 200, "load more" on last page. |
| B2.2 | No Shorts / Live / Streams / Community / Posts tabs | InnerTube browse params per tab; hide a tab if the channel has none. Start with Shorts and Live (they use the same parser or one close to it). |
| B2.3 | Sort: only date (InnerTube) and yt-dlp for others | InnerTube supports popular/oldest params in the browse filter chips; implement them (`handoff-PLAN` T1 already noted `fetch_channel_videos(sort=...)` ignores `sort`: either implement or remove the argument). |
| B2.4 | No filter within a channel | Local filter `f` over loaded entries (title substring, duration range `<5m`, `>20m`), see B7. Search inside channel: InnerTube `/browse` search tab (`params` for the channel search) as a second step. |
| B2.5 | Channel info limited to name, subs, avatar | Show description (first 3 lines), join date, total videos, links, banner as half-block. All in the same `/browse` response, no new request. `a` on the info column to expand. |
| B2.6 | No way to remember a channel without YouTube login | **Local channel bookmarks** (`channels.json`: id, name, avatar url): a "Following (local)" list, so the Subscriptions tab works in `browser: none` mode. Add key e.g. `f`... **[verify key]**: pick from B7. |
| B2.7 | Channel playlist -> open it | Pressing Enter on a channel playlist row should open it as a playable list (`/playlist?list=` via InnerTube browse, yt-dlp fallback) with "Save to local playlist" and "Play all". Today it is a row without a destination. **[verify]** |
| B2.8 | "Play all" / "queue all" | `E` enqueues the whole page/list; also from a channel. The audio queue exists, but there is no bulk add. |
| B2.9 | Back stack | The channel screen is one level deep; opening a channel from a channel's video loses the origin. Keep a stack with breadcrumb `Home › Kurzgesagt › Playlists`. |
| B2.10 | `_channel_id` parsing is string-split on the URL | Replace with a small helper plus tests for `/@handle`, `/c/`, `/user/`, `/channel/`. **[verify]** InnerTube resolve covers `@handle`. |

### B3. Search: history, going back

Today: `/` opens a modal, the query replaces the single Search tab; there is no history; the tab label shows the query; results are cached 30 min
by query hash; InnerTube returns up to 4 pages / 50.

1. **Search stack ("back to previous results").** `_search_query` is a string; make it a stack of `{query, scroll_page, cursor_index}`.
   `Backspace` (or `H`/`Esc` while on Search) pops to the previous query; because `fetch_search_batch` is cache-first, popping is instant.
   Restore the page and cursor, not just the list. Show `‹ 2 of 5 ›` in the breadcrumb.
2. **Search history (persistent).** `search_history.json`, last 100 queries, deduped, with timestamps. In the modal, Up/Down walks history,
   typing filters it (prefix then substring), `Ctrl+D`/`Delete` removes the highlighted suggestion. Config: `search_history: on|off`.
3. **Suggestions as you type** via the anonymous suggest endpoint
   (`suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=`). One request per debounced keystroke (250 ms), shown under the input.
   Privacy note: this sends partial text to Google; make it a setting, default off or at least documented. **[ask]** (E3).
4. **Search tabs and filters.** InnerTube search accepts a `params` filter blob: type (video/channel/playlist), duration, upload date, sort
   (relevance/date/views), live. Expose as `s` (sort) and `t` (type) on the Search tab like the channel's `s`. Today only videos are returned.
5. **More than 50 results.** `SEARCH_FETCH_COUNT = 50` caps at ~4 pages. Follow continuations while the user keeps paging (same live-iterator
   idea as B1.2), cap at 200.
6. **Multiple search tabs.** Optionally allow N search result tabs (like browser tabs) instead of replacing; `F3` cycles. Higher cost; the stack
   in (1) covers the main need. List as stretch.
7. **Result-type rows.** When type=all, mixed channel/playlist/video rows are needed; the list already handles `_is_channel` and
   `_is_playlist` rows, so this is mostly a parser change.

### B4. History: remove, search, YouTube-side history

Local history today: `history.json`, newest first, dedup by id, cap 500, full entry dicts, no delete, no filter.

**Local improvements**

1. **Delete an entry.** `Delete`/`x`? (`x` is audio stop, so it is taken.) Proposal: **`D`** deletes the highlighted history row after one
   confirmation keypress (`Delete? y/N` inline in the action bar, not a modal). `history.remove(id)`. Plural: `Shift+D` clears the whole
   history behind a typed confirmation. **[verify key availability: `D` is unused in `keymap.py`].**
2. **Search/filter history.** `f` (filter) opens an inline filter bar over the list: substring on title + uploader, instant, `Esc` clears.
   Same implementation for Library, Playlist, channel and search results (B7).
3. **Group by day.** Section headers ("Today", "Yesterday", "Mon 9 Nov") as non-selectable rows. History stores `_watched_at`, so this is free.
4. **Resume position.** Record playback position on exit (mpv IPC already reads `time-pos`), store `_resume_s` and `_duration`, show a progress
   bar in the row, and `a`/`v` resume from there (`--start=<s>`). Biggest UX win for long videos. Reset when > 95 % watched.
5. **Watch count and total time** per video (`_plays`, `_seconds`) for a "Most watched" sort. Lets the list stop being only recency.
6. **Cap and retention** become settings (`history_max`, `history_days`); 500 is hardcoded in `history.py`.
7. **Export/import** `termtube --export-history out.json` and import, so history survives a reinstall.

**YouTube-side watch history ("what I watched on YouTube itself")**

yt-dlp already understands this: the extractor shortcut `:ythis` (and the URL `https://www.youtube.com/feed/history`) lists the signed-in
account's history, and it needs cookies, exactly like the Home feed. Check the installed yt-dlp version supports it (`yt_dlp.extractor` ->
`YoutubeHistoryIE`) **[verify]**; if it was removed, fall back to an InnerTube `FEhistory` browse, which is cookie-bound (SAPISIDHASH) and
therefore excluded by the owner decision, in which case the feature is simply not offered.

Design:

- Reuse the Home loader: `FEED_URLS["yt_history"] = "https://www.youtube.com/feed/history"` with `auth=True`, `feed_key="yt_history"`,
  flat extraction, same paging and cache (`cache_ttl.yt_history`, default 10 min: history changes often).
- **UI: a sub-tab on History**: `Local | YouTube`. `Tab` or `[`/`]`-style toggle inside the History tab; do not add an eighth top-level tab. Header
  shows the account's browser and the count loaded.
- **Combined view (optional)** `All`: local + YouTube deduped by id, local `_watched_at` wins; YouTube rows have no exact timestamp (flat
  listing exposes day sections at best **[verify]**), so in the merged view they sort below same-day local entries, flagged with a small `YT`
  badge. Do not pretend YouTube rows have times.
- **Read-only.** Removing an entry from YouTube's history is a write request needing feedback tokens and an authenticated InnerTube call;
  the owner dropped cookie-bearing InnerTube. State this in the UI (`Remove is local only`) and offer `b` to open YouTube's own history page in the
  browser, where removal works.
- **Pause and privacy**: if the account has watch history paused, the page is empty. Show that cause rather than "No items" (the extractor error
  or empty page text can be detected **[verify]**).
- **Import into local**: `I` (or action menu) copies the YouTube history into the local store, skipping duplicates, so the Local view becomes a
  superset. One-time and explicit.
- Policy: extend the cookie table (A1.6). Tests use a recorded fixture of a flat listing; no network, no real profile.

**Same loader gives (cheap once built):** Watch Later, Liked videos, Recommended (B1.8). One "Account" group with a picker instead of one tab each.

### B5. Library: playlists, search, fusion, caching, deleting

Today: scans `.info.json` under `video_dir` and `audio_dir`, merges video and audio by id, sorts by upload date, plays local files directly.
Playlists are a separate tab: `name -> [video ids]`, add/remove through the `p` modal, `create()` on an existing name **resets** it (data-loss
trap **[verify]**: `playlist.create` assigns `data[name] = list(video_ids or [])`; the modal calls `create(name)` for the typed name without checking
that it exists).

**B5.1 Multiple playlists inside Library**
- Rename `Playlists` to a section of Library (see B5.4); a playlist is a named, ordered list of ids plus metadata (C1).
- UI: in the playlist index, `n` new, `R` rename, `D` delete (confirmation), `Enter` open. In a playlist view: `D` removes the item from the
  playlist (not from disk), `J`/`K` move the item down/up (reorder), `m` moves/copies to another playlist.
- Guard `create()` against existing names; make `create` and `rename` separate functions; names are unique case-insensitively.
- The `p` modal gets multi-select (toggle several playlists then `Enter`), and shows `✓` for current memberships (already does).
- Smart/dynamic playlists as saved filters later (e.g. `downloaded audio by uploader X`), stored as a query, not ids.
- Playlist-level actions: play all, shuffle, enqueue all, download all (batch, sequential, with one progress view), export to a `.m3u` for other
  players.

**B5.2 Search within a playlist or the library**
- The shared local filter `f` (B7). Fields: title, uploader/channel, description, tags (sidecars have `tags`), upload year. Syntax:
  free text plus tokens `type:audio`, `type:video`, `dur:<10m`, `by:name`, `year:2024`, `pl:name`, `dl:yes`. Fuzzy ranking (small
  in-memory scorer; no fzf dependency, per project rule).
- Because the Library index (C3) is in memory, filtering 10k rows is instant; no worker needed.
- A global **local search** across History + Library + Playlists (one result list with a source badge) is cheap on the same index; offer it as
  `Ctrl+F`. **[verify key]**

**B5.3 Fusing playlists and Library**
Proposal: one concept, **Collections**, three kinds sharing the list engine:

| Kind | Membership | Source of truth |
|---|---|---|
| Downloaded (the Library) | every file under `video_dir`/`audio_dir` | disk |
| Playlist | explicit ordered ids | `playlists.json` |
| Smart | a saved filter | `playlists.json` (query) |

A playlist row can point at a video that is downloaded or not. Show a state badge: `⬇ video`, `⬇ audio`, `☁` (stream only). Playing an item
uses the local file when one exists, else streams (this already works for the Library because rows carry `_local_path`; for playlist rows resolve
`library.index.get(id)` at load time).
UI shape (pick one, **[ask]**, E2):
- (a) One tab `Library` with a left rail: `All downloads · Videos · Audio · ★ Playlist A · ★ Playlist B`, `Tab` moves between rail and list. Fewest tabs; one place for everything saved.
- (b) Keep two tabs, but make Playlist rows show the download badge, and let the Library tab show "In playlists: A, B" on the detail panel. Smaller change, less fusion.
Recommend (a) with a one-release (b) as the first step.

**B5.4 Video info and thumbnail caching for downloaded items**
Today: the sidecar `.info.json` and the thumbnail downloaded by yt-dlp live next to the media; the thumbnail pipeline checks the disk cache, then the
sidecar thumbnail, then the CDN. The cache for a downloaded item can be pruned (7 days) and the library is re-parsed from the large sidecar
every time.

Proposals:
1. **Library index** `library.json` in the cache dir (C3): per id slim fields (id, title, uploader, channel_id, duration, upload_date, view_count,
   description first 500 chars, tags, `_local_path`, `_audio_path`, `_local_type`, file sizes, sidecar mtime+size, thumbnail path). Rebuild
   incrementally by `(path, mtime, size)`; one `os.scandir` pass instead of `rglob` plus JSON parse of megabytes.
2. **Stable thumbnails for downloaded items.** At download completion (and at index time if missing) normalise the thumbnail: convert `.webp`
   to JPEG at the panel size and store as `<stem>.thumb.jpg` next to the media (or in a `library-thumbs/` cache that housekeeping never prunes).
   `_NON_MEDIA_EXTS` already ignores `.webp`, but PIL needs `webp` support **[verify]**. Offline Library then never touches the network.
3. **Pin on download.** When a download finishes call `cache.pin_video(id, entry)` + `pin_thumb(id)` so a playlist row for a downloaded video keeps
   its title/uploader after the 3-day video-cache prune. Today playlist rows for pruned ids degrade to `{"title": <id>}` (see
   `_load_playlist_videos` fallback): **that is a visible UX bug** for any playlist item added from a video whose cache entry was pruned before pinning.
   More generally: **store title/uploader/duration inside the playlist record** (C1) so a playlist row never shows a bare id.
4. **Missing-file handling.** A sidecar without media still shows a row (documented). Mark it `⚠ file missing` and offer `Remove entry` and
   `Re-download`.
5. **Incremental refresh on download complete** (`invalidate_cache()` is global and forces a full rescan): update the index with the one new item.
6. **Duplicate detection** by id across formats (already merges video+audio); also detect the same id downloaded twice under different names
   (template changes) and offer a clean-up.

**B5.5 Delete entries in Library**
- `D` on a Library row opens a small confirm: `Delete <title>?  [v]ideo file  [a]udio file  [b]oth  [e]ntry only  [Esc]`. Lists the real paths
  (relative to the dir) and sizes so you see what goes. Never deletes without that keypress; trash by default
  (`send2trash`-style: move to the OS trash; **[ask]** whether adding a dependency is acceptable, otherwise a `.termtube-trash/` folder inside the
  download dir, emptied by housekeeping after 30 days).
- Deleting removes the file group (media, `.info.json`, thumbnail, subtitles) via `library.safe_delete` (A1.4), updates the index, removes the
  id from nothing else (playlists keep the id; row becomes `☁`).
- Multi-select (`Space` is audio pause: use `m` mark, `M` mark all on page) then `D` for batch deletion; show a summary count and total size.
- "Free space" view: sort by size, show the total size of the Library in the header.

### B6. Detail panel, player and other widgets (quick wins)

- Persistent mini-player already exists (`AudioBar`); add queue view (`Q`) to see, reorder and remove queued tracks. Today the queue can only
  grow, skip or clear.
- Playback: speed (`<`/`>` are queue-skip so use `Ctrl+[`/`Ctrl+]` or a menu), repeat (one/all), shuffle for playlists, sleep timer.
- Thumbnail: pre-render the next row's thumbnail while idle (the stream prefetch already does this for URLs) to remove the flash when scrolling.
- Mouse: click on page indicator exists; add click-to-sort headers if columns ever exist.
- Help screen is hand-maintained. Generate it from `keymap.py` so a key cannot exist in code but not in help (the rule exists in AGENTS.md; a
  test would enforce it: every binding appears in `help_screen` and `keybindings.md`).

### B7. A shared "list tools" layer (the enabler)

Build once, use in every tab (this is what B2-B5 mostly need):

| Capability | Key (proposal) | Notes |
|---|---|---|
| Filter loaded list | `f` | inline bar at the footer, live; `Esc` clears; keeps cursor on the same id when possible |
| Sort loaded list | `s` | already on Channel; make it a tab-level chooser (date, title, duration, size, watched) |
| Mark / mark page | `m` / `M` | `m` marks and moves down; marked rows get `●` |
| Delete / remove (context-aware) | `D` | History: remove entry; Playlist view: remove from playlist; Library: delete files; Playlist index: delete playlist |
| Move / reorder | `J` / `K` | only in an ordered list (playlist, queue) |
| Undo last destructive action | `u` | keep the last deleted record in memory for 30 s; works for entries, not for files (trash handles files) |

Rule 5 of the keymap ("a key never changes meaning with state") is respected as long as `D` is always "remove this from where I am looking",
and the confirmation text says exactly what it will do. `f`, `m`, `M`, `D`, `J`, `K`, `u`, `Q` are all unused in `keymap.py` today **[verify against `help_screen`, `watch_modal` and each modal's BINDINGS]**.
Update `keybindings.md`, `help_screen.py`, `action_bar.py` in the same change, per AGENTS.md.

---

## Part C. Data model changes

### C1. Playlists (`playlists.json`)

Today `{name: [id, ...]}`. Proposed (versioned, migrated on load, original backed up as `playlists.json.v1`):

```json
{"version": 2,
 "playlists": [
   {"id": "pl_3f9a", "name": "Focus", "created": 1760000000, "updated": 1760001000, "kind": "manual",
    "items": [{"id": "dQw4w9WgXcQ", "title": "…", "uploader": "…", "duration": 212, "added": 1760001000}]}]}
```
Stable playlist ids (rename without breaking references), item snapshots (never a bare id in the UI), ordering is list order.
Write through one locked helper (today `_load`/`_save` is read-modify-write with no lock, unlike `history.py` **[verify]**: two quick toggles
from two screens can lose an update).

### C2. History (`history.json`)

Slim record per item: id, title, uploader, channel_id, duration, thumbnail url, `watched_at`, `plays`, `seconds`, `resume_s`, `source`
(`local`/`yt`). Drop description, formats and the rest; those come from the video cache when needed. File size falls from large to a few
hundred KB at 500 items and load/save stay in single-digit milliseconds. Migration: read old shape, project to slim, write v2.

### C3. Library index

`~/.cache/termtube/library.json`: slim rows (see B5.4) plus `{root, scan_time}`. Invalidate per file by `(mtime, size)`. A fast path checks only the
directories' mtime (as today) then `os.scandir` for changed ones. Provide `library.index` (read-only, in memory), `library.refresh(paths)` and
`library.delete(...)`.

### C4. Search history, channel bookmarks

Small JSON files in the config dir (0600, `atomic_write`), same helper as history. One shared module `src/store.py` with a locked
`JsonStore(path, version, migrate)` class removes the three copies of `_load/_save/_lock` (`history.py`, `playlist.py`, planned others). Fits
AGENTS.md's DRY rule: three real call sites.

---

## Part D. Suggested order

Each step is one or two commits; each leaves `scripts/verify.sh` green.

| Step | Work | Why this order |
|---|---|---|
| 1 | **Measurements first**: startup stage timings (A4.6), Library scan timing with a 500-item fixture, history save timing | Decide with numbers; also checks the [verify] items |
| 2 | **Bug-class fixes**: B1.1 (extension window), A6 paging of local lists, B5.1 `create()` overwrite, `_load_playlist_videos` bare ids | Small, high value, no design needed |
| 3 | **Privacy/security quick set**: A1.2 SponsorBlock hash prefix, A1.1 thumbnail TLS opt-in, A1.7 temp dir, A1.3 template guard | Independent of UX work; a day of work |
| 4 | **`JsonStore` + slim history + history delete + filter + day groups** (C2, C4, B4.1-3) | First user-visible win; builds the list-tools layer (B7) |
| 5 | **Search stack + search history** (B3.1, B3.2) | Answers "go back to previous results" with the cache already in place |
| 6 | **Library index + safe delete + trash** (C3, B5.4, B5.5, A1.4) | Largest perf win; delete needs the safety helper first |
| 7 | **Playlist v2 and management** (C1, B5.1): rename, delete, reorder, multi-add | Needs C4 `JsonStore` |
| 8 | **YouTube history sub-tab** (B4 second half, A1.6) | Reuses the Home loader; small once the policy is recorded |
| 9 | **Fusing Library and Playlists** (B5.3 option b, then a) | Needs 6 and 7 |
| 10 | **Channel: continuations, tabs, bookmarks** (B2) and **Home live iterator** (B1.2) | Biggest engineering; benefits from the earlier measurements |
| 11 | **Settings expansion, cookie prewarm, resume playback, queue view** (A2, A3, B4.4, B6) | Polish layer |

---

## Part E. Questions only you can answer

1. **E1. Keys.** Are `f` filter, `m` mark, `D` delete, `J`/`K` move, `u` undo, `Q` queue acceptable, or do you want a different scheme
    1. acceptable
2. **E2. Library/Playlists shape.** One `Library` tab with a left rail (B5.3a), or two tabs with badges (B5.3b)?
    1. one library with left rail
3. **E3. Search suggestions** send partial text to Google as you type. On, off, or opt-in?
    1. opt-out
4. **E4. Trash.** Move deleted files to the OS trash (needs `send2trash` or per-OS code) or to an in-folder `.termtube-trash/`, or delete outright after the confirmation? 
    1. delete outright AFTER confirmation
5. **E5. Cookie prewarm** (A2) reverses "nothing is read at startup". Acceptable as a setting with default on when a browser is configured?
    1. acceptable
6. **E6. YouTube history** is read-only by design. Is that enough, or do you want removal (needs authenticated InnerTube, which you dropped)?
    1. read-only
7. **E7. Subscriptions feed** (B1.7): the yt-dlp cookie feed (one call), or anonymous per-channel InnerTube fan-out (N calls), or both?
    1. the current design is list the channels, then entering each result goes to the channel page.  I think it is pretty reasonable. no need to change it. 
8. **E8. Scope.** Which of Part B do you want first? The plan above is ordered by value and dependency, but for example the YouTube-history
   tab (step 8) can move to step 4 if it matters most to you.
    1. implement in the order that is the easiest to work and verify.
9. **E9. Dependencies.** Anything beyond the current set (e.g. `send2trash`, a fuzzy matcher like `rapidfuzz`) needs your approval and a
   safe-source check per the project's hard rule; the plan assumes none unless you say yes.
   approved.

---

## Appendix: verification list (things to confirm before building)

1. `_extract_videos` second-call behaviour on Home (`playlistend` vs `skip_ids`), B1.1.
2. `_load_simple_list` -> `add_page(1, all_entries)`: is `PAGE_SIZE` applied to local lists? A6.
3. `playlist.create()` on an existing name from `PlaylistModal.on_input_submitted`. B5.1.
4. Size and contents of a stored history entry (are `formats` or `description` stored?). A1.5, C2.
5. Whether the installed yt-dlp exposes `:ythis` / `feed/history` and what a flat entry carries (timestamp? day section?). B4.
6. Which branch the "sign in" error takes today (`_EXTRACTION_ERRORS` update prompt vs empty feed modal). A2.
7. Temp/IPC directory creation mode and ownership check in `plat.py`. A1.7.
8. `validate_thumb` coverage on the `download_thumbnail` path; PIL webp support. A1.1, B5.4.
9. Unused keys: `f m M D J K u Q` against `keymap.py`, `help_screen.py`, `watch_modal.py`, every modal's `BINDINGS`. B7.
10. Library scan time and sidecar size on a realistic library. A4.3.
