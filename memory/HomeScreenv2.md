# HomeScreen v2 — Rewrite Plan

> Status: **implemented (2026-05-03)** — Steps 1–6, 8 landed in full; Step 7 interim only (mpv `observe_property` final phase deferred to a separate PR).
> Owner: any Claude session.
> Read this top-to-bottom before touching code. Update the "Status" line and check boxes as you go.

---

## 1. Why we're doing this

Opening the home tab spikes CPU to ~30 % on an M4 Pro. Root cause is **fan-out**, not any single slow operation:

- 1 × `yt-dlp stream_flat` on feed load
- 2 × `yt-dlp fetch_full` immediately after first batch reveal (`enrich_in_background(20, max_workers=2)`) — even though every visible field is already in the flat-extract data
- 1 × silent `yt-dlp` background revalidate fired *while serving cache*
- 1 × `chafa --optimize=3 --color-space=din99d` per cursor keystroke, with no kill of the previous process
- `set_interval(0.5, _poll_audio_ipc)` while audio plays, regardless of bar visibility
- `set_interval(600, _scheduled_home_refresh)` regardless of which tab is active

3–5 subprocesses + JSON decoding + chafa dithering converge in a 1–2 s window. Two cores saturate.

**The redesign reduces this to "0 subprocesses on warm open, 1 on cold open, ≤2 alive at any time during use", and gives the UI a calmer, more predictable feel.**

---

## 2. Design principles (do not violate)

1. **Cache is the source of truth.** UI reads only from cache. Network workers only write to cache. No "serve cache and silently refetch in parallel" race.
2. **Lazy by default; eager only on user intent.** Nothing fetches until the user dwells, selects, or refreshes.
3. **One worker per concern, latest-wins.** Cancel stale work *including its subprocess* before starting new.
4. **No timer without a visible reason.** A panel that isn't on screen does not poll, refresh, or render.
5. **Visible freshness beats invisible auto-refresh.** Footer indicator + manual `R` replaces 10-min cron.
6. **Existing behavior preservation:** Title, channel, duration, views, upload-date, thumbnail, description, like count, suppression, history, and all keybindings must still work. This is a *refactor*, not a feature change.

---

## 3. What the user actually sees (UX answers to the open questions)

### 3.1 Detail panel — does it still show details/description/thumbnail?
**Yes — same widgets, same layout, same content.** Only the fetch *timing* changes.

| Field | Source | When it appears |
|---|---|---|
| Title, channel, duration, view count, upload date | flat-extract (already cached) | **Instantly** as soon as cursor lands on the row |
| Thumbnail (rendered) | disk thumbnail + chafa cache or fresh chafa render | After 150 ms cursor dwell. If a cached `(vid, w, h)` ANSI exists → instant. If not → ~200–500 ms after dwell starts. |
| Description, like count, full-res thumbnail URL | `fetch_full` (yt-dlp -j) | After 200 ms cursor dwell. ~300–1500 ms later. Description area shows a single-line "Loading…" placeholder until then. |

What the user perceives:
- Tap `j` to move down → row data + cached thumbnail appear immediately.
- Hold `j` to scroll fast → nothing renders until you stop. No subprocess churn.
- Stop on a row for ¼ second → thumbnail paints, then description fades in.
- Move away mid-load → previous fetch is cancelled (subprocess killed), new one starts. No stale data ever lands in the panel.

This is **strictly better** than today, where every keystroke spawns a chafa + queues a fetch_full that might not finish before you've already moved on.

### 3.2 Home screen on first paint, no user interaction yet

Three cases:

**(a) Cold start — no cache exists**
- List is empty. Header shows `home · loading…` with one small spinner glyph.
- Single `yt-dlp stream_flat` subprocess streams entries. As each arrives it appends to the list.
- Detail panel shows a placeholder: `"Press ↑/↓ to browse · Enter to play"`.
- When the first entry lands, cursor auto-positions on it but **does not** auto-fire detail enrichment until 200 ms dwell — because if the user immediately presses `j`, we'd waste a fetch.

**(b) Warm start — cache fresh (< 10 min old)**
- List paints instantly from cache. Header shows `home · 47 videos · updated 4m ago · R to refresh`.
- Cursor lands on the first item.
- After 200 ms with no input, detail panel auto-populates the first item (1 fetch_full + 1 chafa, total). This is the **only** background work on warm open.
- If the user starts pressing keys before 200 ms, the auto-populate is skipped — focus-driven enrichment takes over naturally.

**(c) Warm start — cache stale (10–60 min)**
- Same as (b) — list paints from cache instantly. Footer reads `updated 23m ago · R to refresh`.
- No automatic refresh. The user decides.

**(d) Warm start — cache very stale (> 60 min)**
- Same as (b/c), but a single quiet refresh fires after the user has dwelled on the home tab for 5 s and is at the top of the list. Header spinner appears for the duration.

There is **never** more than one `yt-dlp` process alive on home open in any of these cases.

---

## 4. New worker topology

Replace the current zoo (`feed_loader`, `bg_refresh`, `thumbnail`, `meta`, `enrich_in_background`'s ThreadPoolExecutor, housekeeping daemon) with **three** screen-owned, exclusive workers + one app-level idle task.

| Worker name | Triggered by | Cancels | Subprocess |
|---|---|---|---|
| `feed`  | cold start, `R` keybind, tab activation if cache > 60 min | previous `feed` worker | `yt-dlp stream_flat` |
| `focus` | cursor dwell ≥ 200 ms | previous `focus` worker + its `yt-dlp fetch_full` Popen | `yt-dlp fetch_full` |
| `thumb` | cursor dwell ≥ 150 ms | previous `thumb` worker + its `chafa` Popen | `chafa` (only on cache miss) |
| `housekeep` (app-level) | app exit OR first 60 s of idle | n/a | none (pure file ops) |

All three screen workers store their `subprocess.Popen` handle on `self` so the next dispatch can `terminate()` them. `@work(exclusive=True)` alone is **not enough** — it only swaps the Python wrapper, the OS process keeps running.

Removed entirely:
- `set_interval(600, _scheduled_home_refresh)` and `_scheduled_home_refresh`
- `_background_refresh_worker` (the stale-while-revalidate path)
- `enrich_in_background` ThreadPoolExecutor (`ytdlp.py:326–364`) — replaced by single-call `fetch_full` from the `focus` worker
- `BatchRevealed` → enrichment fan-out in `MainScreen.on_video_list_panel_batch_revealed`

---

## 5. Action plan (ordered, low risk → high payoff)

Each step is independently revertible. Land them as separate commits. Run the app between steps.

### Step 1 — Drop eager batch enrichment ⚠️ **Biggest win**
- [x] In `src/tui/screens/main_screen.py:480–503`, delete the `on_video_list_panel_batch_revealed` enrichment dispatch (or reduce it to a no-op handler if other code listens for the message).
- [x] In `src/ytdlp.py:326–364`, mark `enrich_in_background` deprecated and remove all callers. Then delete the function and its `ThreadPoolExecutor` import.
- [x] Add a single-shot enrichment dispatch on cursor focus: when `VideoListPanel` posts a `Highlighted`/`Selected`-style message, debounce 200 ms then call a new `_focus_worker(vid)` that runs `ytdlp.fetch_full(vid)` in a `@work(thread=True, exclusive=True, group="focus")` and posts the result back via `call_from_thread`.
- [x] Pre-enrich exactly **one** neighbor in the cursor's last-known direction. Track `_last_cursor_dir: Literal["up","down",None]`. After the focused video's enrichment completes, if `_last_cursor_dir` is set, kick a low-priority enrichment for that single neighbor (still in the `focus` worker — queue depth 1, latest-wins).
- [x] Verify: open home → only `stream_flat` runs. Move cursor → after 200 ms one `fetch_full` runs.

### Step 2 — Chafa output cache + cheaper flags
- [x] Add an LRU dict `self._chafa_ram_cache: OrderedDict[tuple[str,int,int], str]` (~64 entries) on `MainScreen` (or wherever the thumbnail render is dispatched).
- [x] Add disk cache at `~/.cache/termtube/chafa/<vid>_<cols>x<rows>_<fmt>.ansi`. Read first, write on miss. Reuse the existing `~/.cache/termtube/` housekeeping rules.
- [x] In `src/ui/thumbnail.py`, change chafa flags: drop `--color-space=din99d`, change `--optimize=3` → `--optimize=1`. Keep `--color-extractor=average`, `--font-ratio`, `--size`, `--format=symbols`.
- [x] Verify: scroll through 30 items, return to top — no chafa subprocesses spawn for already-seen items at the same panel size.

### Step 3 — Kill stale chafa & fetch_full subprocesses
- [x] In the `thumb` worker, store `self._thumb_proc: subprocess.Popen | None`. Before launching new chafa, `terminate()` previous if alive.
- [x] In the `focus` worker, store `self._focus_proc` and do the same with the `yt-dlp` Popen. `ytdlp.fetch_full` now accepts an `on_proc_started` callback.
- [x] Verify with `ps -ef | grep -E 'chafa|yt-dlp'` while rapidly scrolling: at most one of each lives at a time.

### Step 4 — Replace 10-min `set_interval` with tab-activation freshness check
- [x] Delete the `set_interval(600.0, self._scheduled_home_refresh)` line and the `_scheduled_home_refresh` method.
- [x] In the tab-activation handler, if the cache is older than 60 min and we're at the top of the list, dispatch the `feed` worker after a 5 s delay (`set_timer`, cancellable on tab switch).
- [x] `R` keybind for "force feed refresh now" was already present; left intact.
- [x] Footer Static widget showing `{n} videos · updated {age} · R to refresh` lives in the `VideoListPanel` header. Refreshed every 60 s by a single `Static.update`.

### Step 5 — Remove the stale-while-revalidate path on cache hit
- [x] Delete the call to `_background_refresh_worker` from the cache-hit branch.
- [x] Delete `_background_refresh_worker` itself — no other callers remain.
- [x] Verify: open home with fresh cache → `ps` shows zero `yt-dlp` processes.

### Step 6 — O(1) `update_entry_by_id`
- [x] In `src/tui/widgets/video_list.py`, add `self._items_by_id: dict[str, VideoListItem] = {}` populated alongside `self._items` in `append_entry`.
- [x] Rewrite `update_entry_by_id` to one dict lookup + one `Static.update`. Removed the loop.
- [x] `neighbor_id`, `cursor_index` helpers added at the same time.

### Step 7 — Gate audio poll on bar visibility (interim) → mpv `observe_property` (final)
- [x] **Interim:** Audio poll timer is started/stopped with the audio bar's display state (`_audio_poll_timer` start/stop on transitions). No more unconditional 0.5 s tick.
- [ ] **Final (separate PR):** Replace polling in `src/player.py` with `observe_property` event reader. **Deferred.** Tracked separately; no behaviour change required for HomeScreen v2 to land.

### Step 8 — Move housekeeping to idle/exit
- [x] In `src/tui/app.py`, remove the on-mount housekeeping daemon launch.
- [x] Re-launch via `set_timer(60, _launch_housekeeping)` once after mount. Backstop in `on_unmount` for premature exit.

---

## 6. File-by-file change summary

| File | Change |
|---|---|
| `src/tui/screens/main_screen.py` | Remove `_scheduled_home_refresh`, `_background_refresh_worker`, `on_video_list_panel_batch_revealed` enrichment fan-out, the 10-min `set_interval`, and the unconditional 0.5 s audio poll registration. Add `_focus_worker`, `_thumb_worker` (with Popen tracking), cursor-dwell debounce timers (`_focus_dwell_timer`, `_thumb_dwell_timer`), `_chafa_ram_cache`, footer freshness updater, `R` keybind, tab-activation stale-check, and last-cursor-direction tracking. |
| `src/tui/widgets/video_list.py` | Add `_items_by_id` index. Rewrite `update_entry_by_id` to O(1). `BatchRevealed` message can stay (still used for visibility prefetch logic) but no longer triggers enrichment from the screen. |
| `src/tui/widgets/detail_panel.py` | Remove the per-update `_render_thumbnail_bg` and `_fetch_full_meta_bg` worker dispatch (lines ~135–153, 253–294). The screen now drives both via the `focus`/`thumb` workers and pushes results into the panel via `set_image_path` / `set_ansi` / `update_meta`. The panel becomes a passive view. |
| `src/ytdlp.py` | Delete `enrich_in_background` and its `ThreadPoolExecutor`. Add an `on_proc_started` callback parameter to `fetch_full` (or a new `fetch_full_cancellable`) so the caller can hold the `Popen` for cancellation. |
| `src/ui/thumbnail.py` | Change chafa flags to `--optimize=1` and drop `--color-space=din99d`. Add `(vid, cols, rows)` disk-cache lookup at the top of `render()` and write-on-success. Expose the spawned `Popen` to caller (same pattern as ytdlp). |
| `src/cache.py` | No required changes. Optional: expose `feed_age("home") -> timedelta | None` for the footer freshness label. |
| `src/tui/app.py` | Move housekeeping launch out of `on_mount`. Add idle timer. |
| `src/player.py` | (Step 7 final only) Replace polling poll_audio_properties with `observe_property` event reader. |

---

## 7. Acceptance criteria

A reviewer (or the next Claude) confirms the redesign is done by checking all of:

- [ ] `ps -ef | grep -E 'yt-dlp|chafa'` shows **zero** processes 1 s after warm home open. *(needs human smoke test)*
- [ ] Same check after rapid `jjjjjjjjjj` (cursor scroll) for 2 s shows **at most one chafa and one yt-dlp** at the moment of measurement. *(needs human smoke test)*
- [ ] Cold open: footer reads `home · loading…`; once stream completes, reads `home · N videos · updated just now · R to refresh`. *(needs human smoke test)*
- [ ] Warm open with fresh cache: list paints in <100 ms, footer shows correct age. *(needs human smoke test)*
- [ ] Detail panel: title/channel/stats appear instantly on cursor land; thumbnail and description appear after dwell as described in §3.1. *(needs human smoke test)*
- [ ] Pressing `R` triggers a single visible refresh with header spinner; no other refresh path exists. *(needs human smoke test)*
- [ ] Switching to a non-home tab and back does not spawn `yt-dlp` if cache is fresh. *(needs human smoke test)*
- [ ] Audio playback CPU baseline is lower than today (no 0.5 s poll when not playing; if Step 7 final is done, no poll at all). *(needs human smoke test)*
- [ ] All existing keybindings (watch / dl_video / dl_audio / search / quit / Ctrl+D / etc.) still work. *(needs human smoke test)*
- [ ] Suppression (3-focus rule), history, and library writes still happen — they should fire from the `focus` worker on successful `fetch_full`. *(needs human smoke test)*
- [x] `memory/architecture_decisions.md` updated with the new worker topology and reasoning.
- [x] `memory/active_context.md` updated with the HomeScreen v2 landing.
- [ ] `README.md` and `ROADMAP.md` updated if any user-facing behavior changed (footer freshness, `R` keybind). *(R keybind already documented; footer is a small visual addition — pending user decision on whether to call it out.)*

---

## 8. Things to be careful about

- **Don't lose history/suppression hooks.** Today they fire from inside `DetailPanel.update_entry` (via `cache.register_focus`) and from the audio finished callback. After the refactor, `register_focus` should fire from the `focus` worker (after the 200 ms dwell, not on every cursor move) — otherwise rapid scrolling will not bump focus counts, which is actually a **better** behavior, but confirm with the user that this is intended. The 3-focus suppression rule was designed around dwell, not flicker.
- **Don't break video playback handoff.** `app.suspend()` for `mpv` video must still work. Step 8 (housekeeping) must not interfere with suspend/resume.
- **Don't break the search tab and other tabs.** They share `MainScreen`. The redesign must not regress them. Specifically, the `focus`/`thumb` workers should be tab-agnostic (they care about cursor, not which feed).
- **Cancellable `fetch_full`.** Pass `on_proc_started` through cleanly; don't refactor `ytdlp.fetch_full`'s public signature in a breaking way that affects other callers (library, search, history). Add an optional kwarg defaulting to `None`.
- **Disk chafa cache invalidation.** Key on `(vid, cols, rows)`. If terminal is resized, panel size changes → cache key changes → re-render correctly. Existing `prune_old_thumbnails` housekeeping already handles cleanup, but extend its glob to include `chafa/*.ansi`.
- **Initial focus dispatch on warm open.** Per §3.2(b), schedule a 200 ms one-shot timer to enrich the first item on home mount. Cancel it the moment the user presses any key. This avoids the "user immediately scrolls and we wasted work" trap.
- **Tests / smoke run.** There is no test suite in this project. Manual smoke after each step using `bash setup.sh --sync` then `termtube --debug --level INFO` and watching `$TMPDIR/TermTube/<TIMESTAMP>.log` plus `top -pid $(pgrep -f main.py)` is the QA loop.

---

## 9. Out of scope (do not do as part of this rewrite)

- Switching from yt-dlp to YouTube's InnerTube API.
- Adding new feeds or new tabs.
- Theming changes.
- Replacing chafa with sixel/kitty unconditionally — `textual-image` fallback path stays as it is. Only the chafa branch changes.
- Multi-process pool for `fetch_full` — single in-flight is the entire point of the redesign.

---

## 10. Hand-off checklist for the next session

When you start implementing:
1. Read this file fully.
2. Read `memory/MEMORY.md` and `memory/architecture_decisions.md` for any updates that landed since this plan was written.
3. Confirm the file/line references in §6 still match by spot-checking `main_screen.py`, `ytdlp.py`, `detail_panel.py`. If line numbers drifted, re-anchor by symbol name, not line.
4. Branch off `main` (don't commit straight to it).
5. Implement Step 1 only. Verify acceptance criteria for that step. Commit.
6. Repeat for each subsequent step.
7. Update §5 checkboxes in this file as you land each step (commit the doc with each code change).
8. When all steps land, update `memory/MEMORY.md` with the new worker topology, delete the now-stale entries about `enrich_in_background` and the 10-min refresh, and update `architecture_decisions.md` with a "HomeScreen v2 (May 2026)" section explaining why the fan-out was removed.
