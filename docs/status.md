# Status

**Last updated:** 2026-11-15. Restructure and housekeeping pass, uncommitted on `main`.

## What changed in this pass

- **Structure.** `main_screen.py` (2,146 lines) is a thin screen over mixins in `src/tui/screens/mixins/` (list navigation, detail focus,
  item actions, feed loader, audio player, debug log). `ChannelScreen` uses the same mixins instead of its own copies. `ytdlp.py` is split
  into `ytdlp` (opts, feeds, search, channels), `cookies`, `downloads` and `streams`. Thumbnail loading is one function
  (`src/tui/thumb_loader.py`).
- **Keymap revamped** (`docs/features/keybindings.md`): `hjkl` traversal, `v`/`a` for video/audio, `x` stop, `[ ]` seek; no key changes
  meaning with playback state.
- **Docs.** `AGENTS.md`, `docs/` layout, a `docs/code/` mirror per source file, `docs/decisions/` (migrated from `memory/`), checks in
  `scripts/verify.sh`. Comment blocks moved out of source into the mirrors.
- **Dead code removed:** unused helpers and tests in `cache`, `plat`, `bootstrap`, `updater` (the unwired "yt-dlp updated" notice),
  `history`, `playlist` (`delete`, `rename`), `config`, `deps`, `logger`, widgets and modals; the placeholder snapshot test; stale CSS (1127 to 703 lines).
- **Bugs fixed on the way.** Paging past the last page overwrote that page. Stale audio workers could clear the new track's pending flag.
  History was recorded when mpv spawned, even if playback failed; it is now recorded on the first successful poll. `total_pages` miscounted
  after page eviction. The suppressed-first-batch slice in the home loader skipped rows. The test suite killed pytest (`os._exit` from the quit
  test) and read the real browser cookies.

## Not verified

- Nothing was run against a real terminal, mpv or YouTube. Playback (audio and video), the new keys and the channel page are covered
  by import checks and headless TUI tests only. See `todo.md` item 7.
- The Windows paths (`termtube.cmd`, `setup.ps1`, named pipes) were edited conservatively and not run.

## Known problems

- `DownloadModal` Esc does not stop the running yt-dlp download.
- `play_audio` bumps the audio session before stopping, so the `quit` IPC and socket cleanup target the new session's socket; the old mpv
  is still terminated by process. Mirror: `docs/code/src/tui/screens/mixins/audio_player.py.md`.
- `_extend_feed` and `_stream_view` share one exclusive worker group; paging to the end during the initial home fetch cancels the rest of it.
- `deps.check_dependencies` accepts system `mpv`/`deno`/`ffmpeg`, against the bundled-binaries rule.
- `uninstall.sh` uses `pkill -f termtube` and a stale socket path; `setup.ps1` help lists flags that do not exist; `--update` always exits 0.
- InnerTube fetch errors become empty results (callers fall back to yt-dlp).
- `sort_modal` and `channel_tab_modal` carry hardcoded colours and ignore themes.
- `auto/cookies.txt` (untracked, gitignored) holds browser cookies at the repo root; nothing reads it. Delete it if you do not need it.

Optimization plan step 1 is done: rows with only a video id get a derived `i.ytimg.com` thumbnail URL (`best_thumb_url`).

Step 2 is done: search and channel info use InnerTube with a yt-dlp fallback (live check 2026-11-15: 50 results in 2.7 s, channel info in 0.7–1.0 s). Search shows the first page after about one request and fills in the rest in the background. Channel playlists use InnerTube too, with a yt-dlp fallback (live check 2026-11-15: 80 playlists in 1.0 s).

Step 3 is partly done: the channel page's first page uses `feeds.channel_latest` (RSS with a dead-flag, then InnerTube). RSS still returns 404 on this network (checked with `scripts/bench-sources.py`, both `channel_id` and `UULF` playlist forms; the URL is valid, reports point to a YouTube-side outage), so the InnerTube fallback is what runs here. The Subscriptions tab lists channels, so no merged feed exists.

Cold start (2026-11-15, import path of `main`, 3 runs): app import plus `src.ytdlp` took 319 to 347 ms; with `src.ytdlp` kept off the main thread, 134 to 157 ms. `yt_dlp` itself is imported by the warmup worker thread, so lazy imports inside `ytdlp.py`, `streams.py` and `downloads.py` would not move first paint and were not made. InnerTube requests reuse a per-thread keep-alive connection (about 118 ms per `/player` call after the first, down from 157 to 219 ms).

Cookies are extracted on first authenticated use (home feed, subscription list), narrowed to YouTube and Google, and invalidated on an auth failure; nothing else reads the browser profile.

Stream resolve: no yt-dlp variant beat the baseline by 1.5x (`docs/guides/benchmarks.md`); nothing changed.

Next work: `todo.md`. The optimization plan: `plans/2026-11-15-optimization-PLAN.md`.
