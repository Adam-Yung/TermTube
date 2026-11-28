# Status

**Last updated:** 2026-11-28. `main` holds the de-slopped code (behaviour unchanged, [decisions/quality.md](decisions/quality.md)). The six pipeline jobs, the real-terminal run and the canary against live YouTube (8 of 8) passed on 2026-11-28.

Next: a **Local files** tab.

## What exists

- Every modal is centered and fits the screen; `src/tests/tui/test_layout_audit.py` opens each at five terminal sizes and checks centering, protrusion, overlap and truncated text (`WatchModal` runs with mpv launch and polling stubbed); `test_screen_layout_audit.py` does the same for every main-screen tab, the Library rail and the channel page, and sets the width rules (rail 24, list `9fr` min 40, detail `11fr` min 30, `-narrow` under 100 columns). `test_mixin_wiring.py`, `test_hook_wiring.py` and `test_theme_wiring.py` read the screens' MRO, spy on the real hooks and check CSS selectors against the composed widgets. Error paths, races, 5000-row lists, hostile text and whole-screen journeys have their own suites (`test_loader_errors.py`, `test_races.py`, `test_scale_edge.py`, `test_journeys.py`). The Enter menu and the Actions panel are built from `keymap.ROW_ACTIONS`; the panel lists only what applies to the tab, focus and row ([decisions/ui.md](decisions/ui.md)).
- A Textual TUI with tabs Home, Subscriptions, Search, History, Library, Help (`F1`..`F6`); vim-style keys ([features/keybindings.md](features/keybindings.md)).
- Background audio with queue, seek, SponsorBlock, owned by one controller (`app.audio`); video in an mpv window; downloads (mp4/mp3) and a Library.
- Local history is slim (v2 records, `history` and `history_max` settings, `--clear-history`), written off the UI thread; history and playlists share `src/store.py`; a failed write there never raises: it notifies once and stays dirty. Debug logs are redacted (`logger.redact`).
- Playback remembers where you stopped (`resume_playback`, saved every 5 s of watching and on stop; History rows show `▶ 2:05 / 10:00`), counts time watched, `s` sorts the local History (recent / most watched / longest watched), and `q` opens the audio queue page (reorder, remove, clear, undo, play now); `Ctrl+Q` quits.
- Settings (`,`) has sections for Playback, Downloads, Data, Account and Display, validates typed values with a reason, resets a row with Backspace, and reloads `config.yaml` from disk; `rows_per_page` (10..50) sets the list page size at the next list load.
- Search keeps a session stack of 20 searches (Backspace/Esc returns to the previous results at their page and row) and a persistent history of 100 queries (`search_history` setting) offered in the search prompt, followed by suggestions from Google as you type (on by default, `search_suggestions` setting; the partial text is sent to Google). On the Search tab `s` sorts (relevance / date / views) and `t` picks the type (all / video / channel / playlist; channel rows open the channel, playlist rows say `b`); results come 50 at a time up to 200.
- List tools on the shared list: `f` filter (all loaded pages, live, ranked), `m`/`M` marks, `D` remove after one `y`/N in the action bar, `u` undo for 30 s. History uses all four and shows day headers and a count; Home, Search and Subscriptions answer `D` with a reason (Library `D` deletes files for good after one question, no undo; in a playlist it removes items; on the rail it deletes the playlist). The channel page has the filter only.
- Playlists are v2 (`playlists.json`: ids, slim item snapshots, backup `playlists.json.v1` after migration). The Library tab has a left rail (All downloads, Videos, Audio, one entry per playlist with counts, `+ New playlist`; `Tab` moves between rail and list; a one-line selector on terminals under 100 columns). Playlist keys: `n` new, `R` rename, `D` delete / remove items (undo with `u`), `J`/`K` reorder, `P`/`S`/`E` play / shuffle / queue all; the `p` dialog selects several playlists at once. Playlist rows show `⬇ video` / `⬇ audio` / `⬇ both` / `☁` and play the downloaded file when there is one. The Library filter `f` also takes `type:` `dur:` `by:` `year:` `pl:` `dl:` tokens ([code/src/library_query.py.md](code/src/library_query.py.md)).
- Library, History and Subscriptions share one left side list (`Tab` moves focus, `Enter` loads an entry; each tab opens on its first entry). History: TermTube history (day headers, `D` removes), YouTube history (`:ythis` through the Home loader, `auth=True`, read-only, `YT` badge, no timestamps, ids cached 10 min) and Watch Later (`playlist?list=WL`, read-only); `I` imports the YouTube rows into local history. Subscriptions: Subscribed and Following (local). Without a browser the YouTube sources say they need one.
- Home, YouTube history and Watch Later continue one open yt-dlp listing (`FeedCursor`), prefetch at the second-to-last page, and show `loading 80 more…` then the loaded total in the footer (`[verify live]`: needs a signed-in browser).
- Home hides videos already played, counts them in the footer (`N hidden`) and `Z` toggles them (`played shown`).
- Home shows a cache older than 10 min (`cache_ttl.home_revalidate`) at once and re-reads behind it; new items show as `↑ N new · r to refresh` without moving the cursor.
- Channel page: Videos follow InnerTube continuations (next batch fetched at the second-to-last page, cap 200, footer progress); Shorts and Live tabs appear when the channel has them (checked live 2026-11-18); a playlist row opens its videos in place (play all, enqueue all, save as a local playlist); `B` follows a channel locally and the Following entry of the Subscriptions side list shows those channels; non-date sorts use yt-dlp.
- Playlist pages: Enter on a playlist row in Search or Home opens `ChannelScreen` in playlist mode (header on the left from the first `/browse` page, its videos in the middle, no tabs, sort or follow; `o` opens the owner channel, `P`/`E`/`S` play, queue and save, `first 200 of N shown` past the cap). Mixes (`RD…`) load through `/next` (endless, 200 cap); Home shows playlist and Mix rows (`[verify live]`: needs a signed-in browser). The channel description now shows in full and `i` folds it. [decisions/playlist-page.md](decisions/playlist-page.md).
- Playlist and Mix rows (and Library rail playlists) play in place: `v` video run, `a` audio, `e` queue; `>` `<` step; `<` also returns to the previous audio track. The mpv-window keys are tested against a headless mpv; a real video window is not checked yet.
- Data source ladder: cache, then InnerTube (search, channels, playlists, details), then yt-dlp; account cookies only for Home, the subscription list, YouTube history and Watch Later (the last two read-only)
  ([features/sources.md](features/sources.md), [features/accounts-and-cookies.md](features/accounts-and-cookies.md)). RSS was tried and removed.
- Installers for macOS, Linux and Windows that fetch Deno, ffmpeg and mpv; `--update`, `--refresh`, uninstall scripts ([guides/setup.md](guides/setup.md)).
- Quality gate `scripts/verify.sh` (ruff, about 1300 tests, dead-code check); ratchet gates in `scripts/gate/` (structure, duplication, dead code, mirror freshness, feature ownership, doc size, expiry, growth) and the doc gate (brief, mirrors, links, page freshness); pipeline and weekly canary ([guides/ci.md](guides/ci.md)).

## What has been verified

| Claim | How | When |
|---|---|---|
| Unit, UI and doc checks pass on all three systems | `gate` job on every push | each push |
| The installer, launcher and real mpv work on all three systems | `real-app-unix` / `real-app-windows` jobs | each push |
| The installed app starts, plays, pauses, seeks, stops, records history and quits cleanly in a real terminal | `scripts/e2e-local.py`, 14 steps, hermetic | each push; 10 of 10 runs per platform after the debug-log deadlock fix |
| Live YouTube still parses (search, channel, details, streams) | `scripts/canary-live.py`, weekly, not a gate | 2026-11-28: 8 of 8 |
| Thumbnails, `b`, `y`, `p`, `d`, notifications look and work right | the owner, real terminal, installed app | 2026-11-16 |

## Not verified

- The look of the UI in Windows Terminal, and image thumbnails on Windows and Linux terminals (CI has no graphics protocol).
- A real user's Windows machine (antivirus, proxies, other terminals).
- The Home feed with a real signed-in browser is not automated (it needs the owner's cookies by design).

## Known limits

- Apart from the first page of a search, InnerTube failures read as empty results and the caller falls back to yt-dlp.
- A signed-out browser that YouTube answers with an empty list (no error) shows the empty-feed dialog on Home or Subscriptions; a reported sign-in error shows the sign-in message.
- History stores slim records, including for rows played from the Library. The Library index (`library.json`) is slim too.

Next work: [todo.md](todo.md). Open plans: [plans/](plans/).
