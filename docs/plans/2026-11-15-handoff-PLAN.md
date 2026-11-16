# Handoff plan: remaining work after the 2026-11-15 restructure

For the next agent. Read `AGENTS.md`, `docs/status.md`, `docs/features/architecture.md` and
`docs/plans/2026-11-15-optimization-PLAN.md` (the source ladder and its reasoning) first. This file is the ordered task list with
acceptance criteria. Everything here is to be done except the item listed under "Dropped".

## Rules that bind every task

- **Hard rule (AGENTS.md):** no flagged or unverified downloads. The owner has allowed network access to `youtube.com` and its image CDN for
  measuring and recording fixtures, and nothing else. Anonymous requests only. Never read `auto/cookies.txt`.
- **Never weaken TLS.** `i.ytimg.com` fails verification on the owner's network (a TLS-inspecting proxy). `plat.download_thumbnail` already has
  a documented unverified retry for public images; do not copy that pattern anywhere, and do not add `verify=False` to a benchmark or test.
  The harness blocks it.
- **Model budget (AGENTS.md):** Sonnet or smaller only, never Opus. Work inline; spawn a subagent only for a large independent file set, with
  `model: "sonnet"` and a narrow brief. The token budget is very limited.
- **Cookies:** account cookies never go to InnerTube (`docs/decisions/cookies-and-auth.md`, 2026-11-15). Nothing in this plan may build a
  `SAPISIDHASH` header or put a `Cookie` header on a `youtubei/v1` request.
- Tests never touch the network, the browser profile, or the real `~/.config` / `~/.cache`. Parsers are tested on recorded fixtures.
- Every change: update the `docs/code/` mirror, `docs/status.md`, and append a decision entry when a call was made. Run `scripts/verify.sh`;
  commit only when it prints `GATE-OK`. One logical change per commit.
- Estimates are working time including tests and docs.

## Dropped (owner decision)

Authenticated InnerTube home feed. The home feed and subscription list stay on yt-dlp with the browser cookie jar.

## Tasks, in order

### T1. Channel playlists via InnerTube (1 h)
`ytdlp.fetch_channel_playlists` still uses yt-dlp. Add `innertube.fetch_channel_playlists(channel_id)` using `/browse` with the Playlists
tab params; record one real response (a channel with playlists, e.g. Google Developers `UC_x5XG1OV2P6uZZ5FSM9Ttw`), trim it into
`src/tests/fixtures/innertube_playlists.json`, parse `lockupViewModel` items of type `LOCKUP_CONTENT_TYPE_PLAYLIST` into the same entry
shape `fetch_channel_playlists` returns today (read it first; keep keys the UI uses). Fall back to yt-dlp on empty. Note
`innertube.fetch_channel_videos(sort=...)` ignores `sort`; either implement the "popular" params or remove the argument and make
`ChannelScreen._fetch_videos` stop passing it. 
**Done when:** the channel page's Playlists tab loads through InnerTube (live check, timing in the status doc), parser tests pass on the
fixture, fallback test passes.

### T2. Subscription feed and channel first page: RSS with InnerTube fallback (2.5 h)
**Outcome (2026-11-16): built, then removed.** RSS returned 404 on two networks and in public reports; the channel page uses InnerTube directly. Text below is the original brief.
The benchmark (`docs/guides/benchmarks.md`) saw HTTP 404 on `feeds/videos.xml` for every channel tried. Build
`src/feeds.py`: `channel_latest(channel_id)` tries RSS, falls back to `innertube.fetch_channel_videos`. A module-level "RSS is dead" flag
(set after N consecutive 404s, reset after 30 min) means a dead RSS costs one request, not one per channel. Subscription feed = for each
channel from `fetch_subscribed_channels` (still yt-dlp with cookies, cached 24 h), fetch the latest videos in parallel (pool of 8) and merge
by publish date. Add `FeedLoaderMixin` loading for the `subscriptions` tab if it currently lists channels only: confirm what the tab shows
today before changing UX; if it shows channels, leave that and apply this to the channel page's first page only.
**Done when:** Atom parser and 404 fallback have fixture tests, the dead flag has a unit test with a fake clock, live check shows the
fallback working on this network, and no cookie reaches any request in this module (add a test that asserts no `Cookie` header).

### T3. Lazy, narrowed cookie extraction (1.5 h)
`TermTubeApp.on_mount` starts a thread that extracts browser cookies at startup. Move extraction to first use by the home feed, the
subscription list or an age-gated play. Drop the 10-minute expiry in `src/cookies.py`; re-extract on an auth failure only (yt-dlp raises
a sign-in / 403 error: identify the exception text and invalidate the jar then retry once). Keep only `youtube.com` and `google.com`
cookies in memory, never on disk. Read `docs/decisions/cookies-and-auth.md` first: do not undo "No cookies for stream resolution or downloads".
**Done when:** a session that only searches and plays never reads the browser profile (test with a patched extractor that fails if called),
the jar is shared under one lock (existing concurrency test still passes), the auth-failure retry has a test.

### T4. Make the yt-dlp stream resolve faster (2 h)
Today a resolve costs about 3.0 s (benchmark). Try, measuring each with `scripts/bench-sources.py` (extend it with a row per variant):
(a) one warmed `YoutubeDL` per worker thread, reused; (b) request `140`/`251` directly for audio; (c) pin `extractor_args: youtube:
player_client` to the client that returns direct URLs. Keep what gives at least 1.5x, drop the rest, and record numbers in
`docs/guides/benchmarks.md`. An experimental InnerTube mobile-client `/player` resolve is allowed behind a config flag
(`fast_stream_resolve`, default off) only if it succeeds on at least 19 of 20 public ids and falls back to yt-dlp; it must stay anonymous.
**Done when:** the table in the benchmarks guide shows before/after, the winning variant is wired, tests cover the fallback.

### T5. Cold start (1.5 h)
Measure first: `python -X importtime -m src.main --help 2>&1 | sort -t'|' -k2 -n | tail -20` (check how the entry point is invoked) and
time to first paint with `--debug` logging. Then: lazy-import `yt_dlp` in `src/ytdlp.py`, `src/streams.py`, `src/downloads.py` (keep the
background warmup thread), and replace per-call `urllib.request.urlopen` in `src/innertube.py` with a thread-local keep-alive
`http.client.HTTPSConnection` (reconnect on error, same timeouts). Do not disable certificate verification.
**Done when:** before/after import and first-paint times are in the status doc, all tests pass, innertube tests patch the new transport.

### T6. App-level `AudioController`, one mpv launch path, typed entries (5 h; split into three commits)
1. Move audio state and mpv control out of `AudioPlayerMixin` into an object on `TermTubeApp` (`app.audio`) with the same public methods
   (`play_audio`, `enqueue_audio`, `skip_audio`, `stop_audio`, `toggle_audio_pause`, `seek_audio`, `seek_audio_percent`, `can_enqueue`).
   Screens subscribe through `PlayerStateUpdated`. `ChannelScreen._audio_host` and its `screen_stack` scan go away. Keep the session-counter
   rules in `docs/code/src/tui/audio_controller.py.md`; fix the known socket-path bug while here (`play_audio` bumps the session
   before `_stop_audio`, so the quit IPC and cleanup target the new socket: stop first, then bump).
2. `player.run_mpv_with_retries(cmd_builder, ...)` shared by the audio worker and `WatchModal`; both keep their own command builders.
3. Typed rows: a `TypedDict` per row kind (video, channel, playlist, library) in `src/entries.py`; use them in annotations of the loaders,
   `VideoListPanel` and the mixins. No behavior change.
**Done when:** `ChannelScreen` no longer imports `MainScreen`, audio keeps playing across screen pushes (headless test that pushes a screen
and asserts progress messages still arrive), the retry loop exists once.

### T7. Install `ruff` and gate on it (0.5 h, needs owner approval first)
`pip install` is a download: ask the owner, name the package and version, check its status on PyPI, then add `ruff` to
`requirements-dev.txt`, a minimal `pyproject.toml` / `ruff.toml` (line length 120, rules `E,F,I,UP`), `ruff check` to `scripts/verify.sh`, and
fix the findings. If the owner declines, skip.

### T8. Known problems (4 h total, one commit each)
| Item | Fix | Est. |
|---|---|---|
| `DownloadModal` Esc does not stop a running download | the yt-dlp progress hook already raises on the cancel event (`src/downloads.py`); Esc must set that event (expose a cancel handle from `download_*_with_progress`) | 45 min |
| `deps.check_dependencies` accepts system mpv/deno/ffmpeg | use `bootstrap.is_tool_installed` (bundled only); update the message and tests | 30 min |
| `uninstall.sh`: `pkill -f termtube`, stale `/tmp/termtube-mpv.sock`, lists yt-dlp as a binary | kill by recorded PID or exact name, remove the real socket dir (`plat._unix_ipc_dir`), drop yt-dlp; cannot be run here, so keep edits minimal and `bash -n` it | 30 min |
| `setup.ps1` help lists `-Sync` and `-Deps`; `setup.sh` header lists yt-dlp as bundled | correct the text | 15 min |
| `main --update` always exits 0 | return non-zero when any update failed; test | 15 min |
| `sort_modal` and `channel_tab_modal` have hardcoded colours | move their CSS into `theme.tcss` with the theme variables the other modals use; check all three themes | 30 min |
| `_extend_feed` and `_stream_view` share one exclusive worker group, so paging to the end during the first home fetch cancels it | separate group for `_extend_feed` plus a session check so a stale extend does not apply after a tab switch | 45 min |
| `plat._INSTALL_HINTS["yt-dlp"]` describes the retired binary; `test_platform` asserts it | update both | 10 min |
| Atomic-write helper copied in `history.py`, `playlist.py`, `cache.py` | one helper in `src/plat.py` or `src/fsutil.py` | 20 min |
| `library.all_entries` misses files added in subfolders until `invalidate_cache()` | include subdirectory mtimes in the change check | 20 min |
| `Config._data` reached from outside (`thumbnail_warning_dismissed`) | add `Config.set(key, value)` and use it | 15 min |
| `watch_modal._fmt_secs` duplicates `action_bar._fmt_secs` | one copy in `src/tui/fmt.py` | 10 min |
| `thumbnail_format` accepts `sixel`/`ascii` with no matching renderer | remove the dead values from `Config` and Settings, or implement; prefer remove | 20 min |

### T9. Owner-only checks (not for the agent)
- Real-terminal pass over `docs/features/keybindings.md` on macOS (and Linux/Windows if available): every key, audio start/stop/seek, video,
  channel page, search first-page behaviour.
- Delete `auto/cookies.txt` if unneeded (browser cookies at the repo root, untracked and gitignored).

## Order and total

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8. T8 items are independent and can be done any time. Total about 18 h of agent time (T1 1, T2 2.5,
T3 1.5, T4 2, T5 1.5, T6 5, T7 0.5, T8 4) plus the owner's checks in T9.
