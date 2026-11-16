# src/downloads.py

Offline video and audio downloads through yt-dlp, with progress forwarded to the download modal. Decisions: `docs/decisions/cookies-and-auth.md` (no cookies), `docs/features/` for the user-facing flow.

## Invariants

- Options come from `base_opts(skip_manifests=False)` and never carry cookies: the same degraded-player problem as stream resolution (see `docs/code/src/streams.py.md`).
- `on_progress(text, value)` runs in the download thread. `value` is a percentage, `-1.0` when the total is unknown, or a phase sentinel: `PHASE_NEW_STREAM` (-2) when a new stream starts, `PHASE_POSTPROCESS` (-3) for merge/extract. The UI must marshal to the main thread.
- Cancellation works through the progress hook: it raises `DownloadError` once the registered cancel event is set (`cancel_all()` at exit, or the caller's cancel). The download then returns False.
- Both kinds write `.info.json` and the thumbnail next to the file; the library screen reads them.
- Audio is transcoded to MP3 (`FFmpegExtractAudio`, quality 0); video is merged to mp4. Both need the bundled ffmpeg.

## Limits

`QUALITY_CHOICES` and `AUDIO_QUALITY_CHOICES` are the single source for the quality pickers. A failed download returns False with the reason only in the debug log.
