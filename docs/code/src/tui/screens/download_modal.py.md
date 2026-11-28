# src/tui/screens/download_modal.py

Progress dialog for one yt-dlp download (`downloads.download_video_with_progress` / `download_audio_with_progress`), run in the `download` worker group. Dismisses `True` on success.

- Progress arrives as `(line, pct)`; the sentinel values `downloads.PHASE_NEW_STREAM` and `PHASE_POSTPROCESS` switch the title and bar (second stream, merge/convert).
- Esc sets `_cancelled` and the cancel event passed to the download (`_cancel_event`, created in `on_mount`, released when the worker ends), then dismisses. The progress hook raises on the event, so yt-dlp stops at its next progress callback; the worker ignores later progress and does not dismiss again.
- On success the library cache is invalidated so the next Library open lists the new file. On failure the dialog stays open with the last error line until Esc.

## Audio keys

`Space` and `x` pause and stop background audio while the download runs (a download is long and every other key is blocked by the modal). The hint line shows them only when audio is playing. Esc still cancels the download only.

On success `_on_done` calls `library.finish_download(self._files)` (thumbnail to JPEG, index that one sidecar) and `_pin` stores the slim entry and thumbnail with `cache.pin_video` / `pin_thumb`. `_files` collects the paths from `on_file`. If registering fails, `_registration_failed` logs it, invalidates the Library cache and notifies with the file name; the file is indexed by the next scan.

`_on_progress` runs on the download thread: it forwards the phase to the UI unless cancelled and collects error-looking lines either way; the last one is the failure reason.
