# Status

**Last updated:** 2026-11-16. `main` is green on Linux, macOS and Windows (six pipeline jobs); the weekly canary against live YouTube passed 6 of 6.
The log of how it got here (restructure, optimization steps, measurements): [history/2026-11-16-status-log.md](history/2026-11-16-status-log.md).

## What exists

- A Textual TUI with tabs Home, Subscriptions, Search, History, Library, Playlists, Help; vim-style keys ([features/keybindings.md](features/keybindings.md)).
- Background audio with queue, seek, SponsorBlock, owned by one controller (`app.audio`); video in an mpv window; downloads (mp4/mp3) and a Library.
- Data source ladder: cache, then InnerTube (search, channels, playlists, details), then yt-dlp; account cookies only for Home and the subscription list
  ([features/sources.md](features/sources.md), [features/accounts-and-cookies.md](features/accounts-and-cookies.md)). RSS was tried and removed.
- Installers for macOS, Linux and Windows that fetch Deno, ffmpeg and mpv; `--update`, `--refresh`, uninstall scripts ([guides/setup.md](guides/setup.md)).
- Quality gate `scripts/verify.sh` (ruff, 414 tests, doc checks); pipeline and weekly canary ([guides/ci.md](guides/ci.md)).

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
- `thumbnail_format` has no effect beyond `auto`/`symbols` validation: the renderer is chosen by terminal detection.
- The repository has no LICENSE file (see [todo.md](todo.md)).

Next work: [todo.md](todo.md). Open plans: [plans/](plans/).
