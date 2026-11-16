# Status

**Last updated:** 2026-11-15. The restructure and the handoff plan (`plans/2026-11-15-handoff-PLAN.md`, T1 to T8) are committed on `main`. Open: the owner's real-terminal checks (T9), and `pip install` of `ruff` into the venv.

## What changed in this pass

- **Structure.** `main_screen.py` (2,146 lines) is a thin screen over mixins in `src/tui/screens/mixins/` (list navigation, detail focus,
  item actions, feed loader, audio bar, debug log). `ChannelScreen` uses the same mixins instead of its own copies. `ytdlp.py` is split
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

## Verified in a pty (2026-11-15)

A tmux session (150x46, `browser: none`, throwaway config) ran the real app against YouTube and mpv: home feed, search (50 results, 3 pages), `j` `k`, `l` `g` `G` paging, audio start, seek (`]` `}` `5`), pause, queue (`e`, `>`), stop, channel page (videos, Playlists tab, audio kept playing across it, Esc back), Enter menu, help, settings, tab picker, history entry, `A` quality picker, Ctrl+D, video (`v`, mpv window, `q` stops it), quit with exit code 0 and no stray mpv. It found and fixed: titles with `[brackets]` breaking markup, mangled `[ ]` and `PAUSED` hints. Not covered: `d` download, `b` browser, `y` copy, `p` playlist, Windows and Linux, a Kitty/iTerm2 terminal (tmux has no image protocol, so thumbnails showed the fallback notice), and the unauthenticated home feed only (no cookies read).

## Not verified

- Real terminals other than tmux (iTerm2, Kitty, WezTerm), Linux and Windows. See `todo.md` item 1.
- The Windows paths (`termtube.cmd`, `setup.ps1`, named pipes) were edited conservatively and not run.

## Known problems

- InnerTube fetch errors become empty results (callers fall back to yt-dlp).

Optimization plan step 1 is done: rows with only a video id get a derived `i.ytimg.com` thumbnail URL (`best_thumb_url`).

Step 2 is done: search and channel info use InnerTube with a yt-dlp fallback (live check 2026-11-15: 50 results in 2.7 s, channel info in 0.7–1.0 s). Search shows the first page after about one request and fills in the rest in the background. Channel playlists use InnerTube too, with a yt-dlp fallback (live check 2026-11-15: 80 playlists in 1.0 s).

Step 3 is partly done: the channel page's first page uses `feeds.channel_latest` (RSS with a dead-flag, then InnerTube). RSS returns 404 for every channel, URL form and user agent, from two machines (`scripts/diagnose-rss.py`, 2026-11-16); the 404 is served by YouTube's own `YouTube RSS Feeds server`, so it is a YouTube-side outage, not our request. The InnerTube fallback is what runs (30 entries with durations in about 0.3 to 0.5 s). The Subscriptions tab lists channels, so no merged feed exists.

Cold start (2026-11-15, import path of `main`, 3 runs): app import plus `src.ytdlp` took 319 to 347 ms; with `src.ytdlp` kept off the main thread, 134 to 157 ms. `yt_dlp` itself is imported by the warmup worker thread, so lazy imports inside `ytdlp.py`, `streams.py` and `downloads.py` would not move first paint and were not made. InnerTube requests reuse a per-thread keep-alive connection (about 118 ms per `/player` call after the first, down from 157 to 219 ms).

Audio lives on `app.audio` (`AudioController`, `src/tui/audio_controller.py`); screens mirror it through broadcast messages, `ChannelScreen` no longer scans the screen stack, and the old socket-path bug (stop after the session bump) is fixed.

Rows have declared shapes (`src/entries.py`, annotations only); one mpv launch loop (`player.run_mpv_with_retries`) serves audio and video.

`ruff check .` is part of the gate (`ruff.toml`). The checkout's `.venv` has no ruff yet: an earlier bare `pip install` went into the installed app's venv. Run `scripts/dev-setup.sh --recreate`; until then the gate takes `RUFF=<path>`. See `docs/guides/environments.md`.

Cookies are extracted on first authenticated use (home feed, subscription list), narrowed to YouTube and Google, and invalidated on an auth failure; nothing else reads the browser profile.

Stream resolve: no yt-dlp variant beat the baseline by 1.5x (`docs/guides/benchmarks.md`); nothing changed.

Next work: `todo.md`. The optimization plan: `plans/2026-11-15-optimization-PLAN.md`.
