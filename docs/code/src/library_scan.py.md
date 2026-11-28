# src/library_scan.py

Reads the download folders for `src/library.py` (its only caller): the walk, sidecar parsing, per-root entries and the video/audio merge.
Split from `library.py`. It owns no state; the persisted index and the cache stay in `library.py`.

`scan_root` reads one root in one `os.scandir` walk (`_walk`; symlinked files and folders are neither followed nor listed). A sidecar whose
`(mtime, size)` equals its index record is not read; new or changed ones are parsed (`parse_sidecar`); records of vanished sidecars drop out. A
sidecar that is unreadable, is not JSON or has no `id` is skipped with a debug log.

Fields added per entry at build time (never stored): `_sidecar_path`, `_local_type` (`video` or `audio`, by the root the sidecar is in),
`_local_path` and `_size` (media file with the sidecar's stem in the same folder), `_thumb_path` (image with that stem, `.jpg` preferred),
`_missing_file=True` when there is a sidecar but no media. Media without a sidecar is not listed. The same id in both roots is one row (video
row): `_has_audio`, `_audio_path`, `_audio_size`, `_audio_sidecar_path`. When the video file is gone but the audio exists the audio row wins.
`merge` sorts by `upload_date` descending. Because paths come from the walk, a sidecar cannot point a row at another file.
