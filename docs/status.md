# Status

**Last updated:** 2026-11-17. `main` is green on Linux, macOS and Windows (six pipeline jobs); the weekly canary against live YouTube passed 6 of 6.
The log of how it got here (restructure, optimization steps, measurements): [history/2026-11-16-status-log.md](history/2026-11-16-status-log.md).

## What exists

- A Textual TUI with tabs Home, Subscriptions, Search, History, Library, Help (`F1`..`F6`); vim-style keys ([features/keybindings.md](features/keybindings.md)).
- Background audio with queue, seek, SponsorBlock, owned by one controller (`app.audio`); video in an mpv window; downloads (mp4/mp3) and a Library.
- Local history is slim (v2 records, `history` and `history_max` settings, `--clear-history`), written off the UI thread; history and playlists share `src/store.py`.
- Playback remembers where you stopped (`resume_playback`, saved every 5 s of watching and on stop; History rows show `▶ 2:05 / 10:00`), counts time watched, `s` sorts the local History (recent / most watched / longest watched), and `Q` opens the audio queue (reorder, remove, undo, play now).
- Settings (`,`) has sections for Playback, Downloads, Data, Account and Display, validates typed values with a reason, resets a row with Backspace, and reloads `config.yaml` from disk; `rows_per_page` (10..50) sets the list page size at the next list load.
- Search keeps a session stack of 20 searches (Backspace/Esc returns to the previous results at their page and row) and a persistent history of 100 queries (`search_history` setting) offered in the search prompt, followed by suggestions from Google as you type (on by default, `search_suggestions` setting; the partial text is sent to Google). On the Search tab `s` sorts (relevance / date / views) and `t` picks the type (all / video / channel / playlist; channel rows open the channel, playlist rows say `b`); results come 50 at a time up to 200.
- List tools on the shared list: `f` filter (all loaded pages, live, ranked), `m`/`M` marks, `D` remove after one `y`/N in the action bar, `u` undo for 30 s. History uses all four and shows day headers and a count; Home, Search and Subscriptions answer `D` with a reason (Library `D` deletes files for good after one question, no undo; in a playlist it removes items; on the rail it deletes the playlist). The channel page has the filter only.
- Playlists are v2 (`playlists.json`: ids, slim item snapshots, backup `playlists.json.v1` after migration). The Library tab has a left rail (All downloads, Videos, Audio, one entry per playlist with counts, `+ New playlist`; `Tab` moves between rail and list; a one-line selector on terminals under 100 columns). Playlist keys: `n` new, `R` rename, `D` delete / remove items (undo with `u`), `J`/`K` reorder, `P`/`S`/`E` play / shuffle / queue all; the `p` dialog selects several playlists at once. Playlist rows show `⬇ video` / `⬇ audio` / `⬇ both` / `☁` and play the downloaded file when there is one. The Library filter `f` also takes `type:` `dur:` `by:` `year:` `pl:` `dl:` tokens ([code/src/library_query.py.md](code/src/library_query.py.md)).
- The History tab has sources, `Y` cycles them: Local (day headers, `D` removes), Watch Later (`playlist?list=WL`, same loader, read-only) and YouTube (`:ythis` through the Home loader, `auth=True`, read-only, `YT` badge, no timestamps, ids cached 10 min); `I` imports the YouTube rows into local history. Without a browser the YouTube source says it needs one.
- Data source ladder: cache, then InnerTube (search, channels, playlists, details), then yt-dlp; account cookies only for Home, the subscription list, YouTube history and Watch Later (the last two read-only)
  ([features/sources.md](features/sources.md), [features/accounts-and-cookies.md](features/accounts-and-cookies.md)). RSS was tried and removed.
- Installers for macOS, Linux and Windows that fetch Deno, ffmpeg and mpv; `--update`, `--refresh`, uninstall scripts ([guides/setup.md](guides/setup.md)).
- Quality gate `scripts/verify.sh` (ruff, 526 tests, doc checks); pipeline and weekly canary ([guides/ci.md](guides/ci.md)).

## What has been verified

| Claim | How | When |
|---|---|---|
| Unit, UI and doc checks pass on all three systems | `gate` job on every push | each push |
| The installer, launcher and real mpv work on all three systems | `real-app-unix` / `real-app-windows` jobs | each push |
| The installed app starts, plays, pauses, seeks, stops, records history and quits cleanly in a real terminal | `scripts/e2e-local.py`, 14 steps, hermetic | each push; 10 of 10 runs per platform after the debug-log deadlock fix |
| Live YouTube still parses (search, channel, details, streams) | `scripts/canary-live.py`, weekly, not a gate | 2026-11-16: 6 of 6 |
| Thumbnails, `b`, `y`, `p`, `d`, notifications look and work right | the owner, real terminal, installed app | 2026-11-16 |

## Not verified

- The look of the UI in Windows Terminal, and image thumbnails on Windows and Linux terminals (CI has no graphics protocol).
- A real user's Windows machine (antivirus, proxies, other terminals).
- The Home feed with a real signed-in browser is not automated (it needs the owner's cookies by design).

## Known limits

- InnerTube fetch errors become empty results; callers then fall back to yt-dlp.
- `sponsorblock.py` still falls back to an unverified TLS context when certifi and the system store both fail to build (separate from the thumbnail setting, which is now opt-in).
- A sign-in failure on Home or Subscriptions shows the empty-feed dialog, not a "sign in again" message.
- History stores slim records, including for rows played from the Library. The Library index (`library.json`) is slim too.

Next work: [todo.md](todo.md). Open plans: [plans/](plans/).
