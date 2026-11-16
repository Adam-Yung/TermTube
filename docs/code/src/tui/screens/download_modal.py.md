# src/tui/screens/download_modal.py

Progress dialog for one yt-dlp download (`downloads.download_video_with_progress` / `download_audio_with_progress`), run in the `download` worker group. Dismisses `True` on success.

- Progress arrives as `(line, pct)`; the sentinel values `downloads.PHASE_NEW_STREAM` and `PHASE_POSTPROCESS` switch the title and bar (second stream, merge/convert).
- Esc sets `_cancelled` and the cancel event passed to the download (`_cancel_event`, created in `on_mount`, released when the worker ends), then dismisses. The progress hook raises on the event, so yt-dlp stops at its next progress callback; the worker ignores later progress and does not dismiss again.
- On success the library cache is invalidated so the next Library open lists the new file. On failure the dialog stays open with the last error line until Esc.
