# Playback

mpv control, audio and video launch paths, SponsorBlock, and playback start latency.

## 2026-04-25 — mpv via IPC instead of blocking subprocess

`mpv` launches with `--input-ipc-server` pointing at a Unix socket (`/tmp/termtube-mpv-audio.sock`). Commands (seek, pause, quit) go as JSON over the socket, so every interaction is non-blocking. A blocking `subprocess.run(mpv)` would freeze the Textual event loop, because Textual updates the UI on a single thread.

Full-screen video playback uses `app.suspend()` instead. It yields the terminal to mpv and restores the TUI on mpv exit. IPC is only for background audio.

## 2026-04-25 — `app.suspend()` for video, IPC for audio

- Video needs the full terminal. `app.suspend()` hands control over cleanly and restores Textual state on return.
- Audio is headless and the TUI must stay interactive during playback, so IPC is the only viable approach.

## 2026-05-03 — mpv stderr captured via `PIPE`, drained with `communicate()`

`subprocess.DEVNULL` made silent mpv failures look like finished playback: an "Audio finished" toast after 3 seconds with no audio. To diagnose them, mpv now runs with `--msg-level=all=error` and stderr goes to `PIPE`.

`communicate()` drains stderr concurrently with the wait. Reading stderr after `wait()` can deadlock: mpv can fill a 64 KiB pipe buffer with a chain of yt-dlp errors and block waiting for a reader.

The exit code drives a tri-state branch: success, user-stopped, failure. Only failures bypass history and show a notification with the first stderr line.

## 2026-05-10 — SponsorBlock segments: fetch, cache and auto-skip

- **Simple `videoID` endpoint, not the privacy-preserving hash prefix.** The full video ID is already known, so the hash prefix adds complexity for no privacy gain (yt-dlp already fetched the video).
- **Segments fetched in the existing worker thread.** Audio fetches inside `_launch_audio_worker` (already `@work(thread=True)`). Video fetches inside `_launch_video`. No new worker.
- **Disk cache at `~/.cache/termtube/sb/{video_id}.json`, 24 h TTL.** It avoids redundant API calls on re-listen. A 404 (video has no segments) caches an empty list so it is not retried.
- **Progress bar renders character by character when segments exist.** Each column maps to a time range. Columns overlapping a segment render green. Otherwise it uses normal playback color. With no segments it falls back to the original fast path, string multiplication.
- **Auto-skip uses a `_skipped_indices: set[int]` guard.** It stops one segment from triggering repeated seeks when the poll fires before mpv finishes seeking past the boundary.
- **`urllib.request` (stdlib) instead of `httpx`/`requests`.** No new dependencies. A 3 s timeout keeps a slow or down API from noticeably delaying playback start.
- **Configuration is a nested dict (`sponsorblock:` key in config.yaml).** It mirrors the `cache_ttl` pattern. It is deep-merged on load so partial user overrides do not clobber other defaults.

## 2026-05-16 — mpv.net rejected for headless audio on Windows

mpv.net (`mpvnet.exe`) is a fork that always opens a GUI window, even with `--no-video --force-window=no --no-terminal` and the Windows `CREATE_NO_WINDOW` Popen flag. Those flags suppress the console window. The video window is a top-level GUI window controlled by the build, not by mpv's window flags.

The mpv.net install dir also ships a stub `mpv.exe` that redirects to `mpvnet.exe`. A naive `shutil.which("mpv")`, or a search for `mpv.exe` near mpv.net, binds to the shim and the user sees a popup on every audio play.

The fix has two layers:

1. `setup.ps1` no longer maps `mpv → mpv.net` in `$WinGetPackages`. `Install-MpvCli` downloads the real upstream CLI build from `zhongfly/mpv-winbuild` to `%LOCALAPPDATA%\TermTube\mpv\mpv.exe`.
2. On Windows, `_mpv_exe(headless=True)` in `src/player.py` returns only:
   - the TermTube-bundled standalone `mpv.exe`, or
   - a PATH `mpv.exe` with no `mpvnet.exe` sibling (`_is_real_cli_mpv` detects the shim by inspecting the parent dir).
   - Otherwise it returns `None`, and the audio worker shows an error telling the user to re-run `setup.ps1`.

Rejected alternative: spawn mpv.net hidden and call Win32 `ShowWindow(SW_HIDE)` after launch. mpv.net renders its window in a separate thread that creates a fresh visible HWND on every property change.

## 2026-07 — Play-pending guard for the audio race

Between `_start_audio()` and the mpv subprocess spawn (1–3 s of URL resolution), `_audio_proc` is None. The old guard `_audio_playing` only checked `_audio_proc.poll()`, so a second play press could slip through.

Fix: `_start_audio` sets a `_play_pending` boolean immediately, and the `_audio_playing` property includes it. It clears on every exit path: subprocess spawn, mpv not found, OS error, session mismatch. The guard needs no busy-wait or queue.

## 2026-08-20 — Playback latency: CDN probe and cache poll

Problem: three stability mechanisms stacked sequentially and blocked playback start for about 6 s:
1. Cache poll loop (6 × 500 ms = 3 s) waiting for background prefetch.
2. CDN readiness fallback sleep (5 s) when no probe event existed.
3. Retry inter-attempt sleep (1.5 s).

Fix:
- Cache poll is a single 1 s wait. It still avoids a concurrent yt-dlp for the same video.
- CDN warmup timeout drops from 5.0 s to 1.5 s.
- With no probe event (inline resolve), start a probe immediately and wait on it (max 1.5 s) instead of sleeping blind.
- Skip the CDN wait when the URL came from the prefetch cache, because the probe already ran in the background.
- Retry sleep drops from 1.5 s to 1.0 s.

Why it is safe: the CDN background probe still runs on every `put_cached_stream_url()`. In the happy path (user dwells 2–3 s before play), the probe finishes well before playback is requested. mpv also runs with `--cache=yes --demuxer-readahead-secs=30`, which absorbs residual CDN warmup at the transport layer.

## 2026-11-15 — No faster yt-dlp stream resolve; no InnerTube mobile resolve

Measured warmed reuse, direct `140/251`, manifest skipping and four `player_client` pins against the baseline (`docs/guides/benchmarks.md`). None gave 1.5x, so none is wired. The optional InnerTube mobile-client `/player` resolve behind `fast_stream_resolve` was not built: `/player` returns no `streamingData` without a Proof of Origin token (`docs/code/src/innertube.py.md`), and the clients that skip that check (`tv`, `ios`) failed every resolve above. Revisit if yt-dlp's default client changes.

## 2026-11-15 — Audio moved to an app-level `AudioController`

State and mpv control left `AudioPlayerMixin` (on `MainScreen`) for `AudioController` on `TermTubeApp` (`app.audio`). Screens mirror it through messages the controller broadcasts to every screen on the stack, so a covered screen's bar stays current and no screen finds another by scanning `screen_stack`. Workers are plain daemon threads, and the poll keeps its old "one at a time" behaviour with a busy flag. Two fixes came with the move: `play_audio` stops the old track before the session counter moves (the `quit` IPC and cleanup used to hit the new socket), and the socket path is derived from the session a worker holds, not the current one. A launch failure of an older track no longer stops the newer track.

## 2026-11-15 — One mpv launch loop

`player.run_mpv_with_retries` replaced the two copies of the spawn, wait and retry loop (audio controller, `WatchModal`). It returns an outcome and each caller keeps its own reaction. Two small behaviour changes: audio processes are now unregistered from `ProcessRegistry` when they exit (only video were), and video also stops retrying as soon as the modal is stopped, after an exit as well as before a launch.

## 2026-11-16 — Local files play directly; mpv errors are no longer swallowed

The first Windows run of the real-app pipeline played nothing from the Library: mpv exited with code 2 three times and the app reported "no stderr output". The command carried `--ytdl-format=ba/b` for a plain `.wav`, and `--no-terminal` had silenced mpv's own error. Two changes. A local file is now handed to mpv as a direct file (`--no-ytdl -- path`, the same form stream URLs already use), for audio and video; ytdl options are only for page URLs. The audio command uses `--no-input-terminal` instead of `--no-terminal` and mpv gets `stdin=DEVNULL`, so mpv still cannot read the TUI's keys but its errors reach the captured stderr and the failure notice. Which of the two caused the Windows exit code was not isolated; the next pipeline run shows whether playback now works or reports the real error.

## 2026-11-17 — SponsorBlock uses the hash-prefix endpoint

`fetch_segments` calls `/api/skipSegments/<first 4 hex chars of sha256(videoID)>` and filters the response for the exact `videoID` locally. The old `?videoID=` query told a third party every video played, which is a watch history; the prefix reveals a bucket of roughly 65 000 possible ids. Cost: a larger response (every video in the bucket that has segments), still well inside the 3 s timeout. The `ssl_pref` fallback to an unverified context in the same module is a separate privacy and integrity issue, not changed here.

## 2026-11-17 — SponsorBlock never falls back to unverified TLS

When neither the certifi nor the system context builds, `sponsorblock` returns no skip segments (debug log) instead of disabling certificate checks. A saved `unverified` preference from an older build is ignored. Reason: a man-in-the-middle could otherwise inject skip ranges; losing skips is the cheaper failure.

## 2026-11-18 — Resume, watch time and the queue view

**Resume lives in the history record**, not in a new file: `resume_s` and `seconds` were already placeholders in the v2 record, so there is no schema change and `history_max`, undo and `--clear-history` apply for free. The cost is that resume needs History on (no record, no resume). It is written from the poll loop that already exists, by `ProgressTracker` (`src/progress.py`), every 5 s of *watched* time instead of every N seconds of wall clock, so the debounce does not depend on the clock and is testable without sleeping; the store's own deferred write coalesces the disk. Quit calls `history.flush()` because the force-exit timer uses `os._exit`.

**Thresholds.** No resume below 10 s or from 95 %; a natural end clears it; live streams never record or resume. Watch time ignores steps over 3 s between polls (seeks, SponsorBlock skips) and zero steps (pause). `--start` is built in one place, `player.start_args`.

**Queue view.** `AudioController` stays the only owner of queue state: four small methods (`move_queued`, `remove_queued`, `insert_queued`, `play_queued`) and a modal that redraws from `app.audio.queue` on the controller's broadcasts. Choices: the playing track is shown but is not editable (`>` and `x` already end it, and removing it would need a rule for what plays next); `Enter` plays the chosen track now and leaves the tracks before it queued, like `a`; undo is local to the dialog.

**History sort** (`s` on the local History tab) reuses `SortModal` and the existing `s` key, which is a hint elsewhere. The two non-recent orders drop the day headers. The choice lasts for the session. This needed a small change in `FeedLoaderMixin._stream_view` (the History branch), the one place the order is applied at load.

## 2026-11-27 — The queue is a page on `q`; `Ctrl+Q` quits

The `Q` popup was easy to miss and showed no details. `q` now opens `QueueScreen`, a list-and-detail page like a playlist's, and quit moved to `Ctrl+Q` (Textual's own binding, overridden to keep our cleanup). Rejected: keeping the popup and only moving it to `q`. `c` clears the upcoming tracks only, so it needs no confirmation: `u` brings them back and `x` already stops everything. `c` means "channel" elsewhere; the queue page has no channel key. Starting a queued track now removes it from the queue, because the page identifies rows by video id.
