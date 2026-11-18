# Status

**Last updated:** 2026-11-17. `main` is green on Linux, macOS and Windows (six pipeline jobs); the weekly canary against live YouTube passed 6 of 6.
The log of how it got here (restructure, optimization steps, measurements): [history/2026-11-16-status-log.md](history/2026-11-16-status-log.md).

## What exists

- A Textual TUI with tabs Home, Subscriptions, Search, History, Library, Playlists, Help; vim-style keys ([features/keybindings.md](features/keybindings.md)).
- Background audio with queue, seek, SponsorBlock, owned by one controller (`app.audio`); video in an mpv window; downloads (mp4/mp3) and a Library.
- Local history is slim (v2 records, `history` and `history_max` settings, `--clear-history`), written off the UI thread; history and playlists share `src/store.py`.
- List tools on the shared list: `f` filter (all loaded pages, live, ranked), `m`/`M` marks, `D` remove after one `y`/N in the action bar, `u` undo for 30 s. History uses all four and shows day headers and a count; Home, Search, Subscriptions, Library and Playlists answer `D` with a reason (Library and Playlists get delete in Phases 4 and 5). The channel page has the filter only.
- Data source ladder: cache, then InnerTube (search, channels, playlists, details), then yt-dlp; account cookies only for Home and the subscription list
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
- History stores the row as played; a row played from the Library carries the whole sidecar (large file).

Next work: [todo.md](todo.md). Open plans: [plans/](plans/).
