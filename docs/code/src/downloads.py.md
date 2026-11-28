# src/downloads.py

Offline video and audio downloads through yt-dlp, with progress forwarded to the download modal. Decisions: `docs/decisions/cookies-and-auth.md` (no cookies), `docs/features/` for the user-facing flow.

## Invariants

- Options come from `base_opts(skip_manifests=False)` and never carry cookies: the same degraded-player problem as stream resolution (see `docs/code/src/streams.py.md`).
- `on_progress(text, value)` runs in the download thread. `value` is a percentage, `-1.0` when the total is unknown, or a phase sentinel: `PHASE_NEW_STREAM` (-2) when a new stream starts, `PHASE_POSTPROCESS` (-3) for merge/extract. The UI must marshal to the main thread.
- Cancellation works through the progress hook: it raises `DownloadError` once the cancel event is set (`cancel_all()` at exit, or the `cancel` event the caller passes to `download_*_with_progress`; the caller creates it with `ytdlp.new_cancel_event()` so quit still cancels it). The download then returns False. The abort happens at the next progress callback, so a stalled connection ends at the socket timeout.
- Both kinds write `.info.json` and the thumbnail next to the file; the library screen reads them.
- Audio is transcoded to MP3 (`FFmpegExtractAudio`, quality 0); video is merged to mp4. Both need the bundled ffmpeg.
- The yt-dlp hooks are module functions bound with `functools.partial` per download (`_make_progress_hook`, `_make_postprocessor_hook`).

## Limits

Output templates are checked twice. `check_template` (called by `_outtmpl`, and by Settings when a template is edited) rejects an absolute path, a drive, or a `..` part before yt-dlp starts (the download dialog shows the `RuntimeError` text). `_StayInside` is a yt-dlp postprocessor at stage `video` (before the filename is used and before any file is written) that refuses a computed path outside the configured directory, which a field can cause even with a safe template: a title that is exactly `..` becomes a `..` path component. That second refusal is a `DownloadError`, so it reads as a failed download with the reason in the debug log.

`QUALITY_CHOICES` and `AUDIO_QUALITY_CHOICES` are the single source for the quality pickers. A failed download returns False with the reason only in the debug log.

## Finished files
`download_video_with_progress` and `download_audio_with_progress` take `on_file(path)`: called for every file yt-dlp finishes (progress hook `finished`, postprocessor hook `finished` with `info_dict.filepath`), so the caller learns the final media file without scanning. The download modal passes the list to `library.finish_download`.
