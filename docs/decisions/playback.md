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
