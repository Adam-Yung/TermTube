# src/library.py

Data for the Library page: a slim index of the `.info.json` sidecars yt-dlp writes next to each download in `video_dir` and `audio_dir`,
plus deletion of a row's files. Callers: the library feed loader and the Library removal handler (`all_entries`, `safe_delete`, `forms`,
`form_sizes`, `total_size`), the download modal (`refresh` / `finish_download` after a download), the detail panel and list rows.

## The index

`INDEX_PATH` (`library.json` in the cache dir, a `JsonStore`, version 1) maps `sidecar path -> {mtime, size, entry}`. `entry` is slim: id,
title, uploader, channel, channel_id, duration, upload_date, view_count, webpage_url, tags, thumbnail URL and `description` cut to 500
characters. Never `formats`. It reuses `history.slim` for the common fields, so there is one slimming helper.

`all_entries` rebuilds in one `os.scandir` walk per root (`_walk`; symlinked files and folders are neither followed nor listed). A sidecar whose
`(mtime, size)` equals its index record is not read; new or changed ones are parsed (`_parse`); records of vanished sidecars drop out. A
sidecar that is unreadable, is not JSON or has no `id` is skipped with a debug log.

Fields added per entry at build time (never stored): `_sidecar_path`, `_local_type` (`video` or `audio`, by the root the sidecar is in),
`_local_path` and `_size` (media file with the sidecar's stem in the same folder), `_thumb_path` (image with that stem, `.jpg` preferred),
`_missing_file=True` when there is a sidecar but no media. Media without a sidecar is not listed. The same id in both roots is one row (video
row): `_has_audio`, `_audio_path`, `_audio_size`, `_audio_sidecar_path`. When the video file is gone but the audio exists the audio row wins.
Sorted by `upload_date` descending. Because paths come from the walk, a sidecar cannot point a row at another file.

## Cache

`all_entries` also keeps the built list per `(video_dir, audio_dir)` and returns it while `_dir_mtime` (newest mtime over the directories of
each tree) is unchanged. `invalidate_cache()` drops the list; the index still saves the parsing. `refresh(paths)` takes the media files a
download finished, parses only their sidecars into the index and drops the list. `_lock` serializes rebuilds; call from a worker.

## After a download

`normalise_thumbnail(media)` makes the thumbnail yt-dlp wrote a JPEG named after the media (PIL converts webp and png; if conversion fails
the original stays). `finish_download(paths)` normalises, calls `refresh` and returns the slim entry (with `_local_path`, `_thumb_path`) for
the modal to pin in the cache.

## Deleting

`safe_delete(entry, roots, which)` with `which` in `video | audio | both` returns a `DeleteResult` (`removed`, `failed` as
`(path, reason)`, `freed`). Per form it removes the media, its `.info.json`, and images/subtitles with exactly that stem (`stem.jpg`,
`stem.en.vtt`). A row whose media is missing (`_missing_file`) deletes its sidecar group whatever `which` is. If another media file with the same stem survives in the same folder
the form's sidecar and extras are kept. Every path is checked by `_refusal`: no `..`, inside a configured root, no symlink anywhere below the
root; refusals land in `failed` and nothing else is touched. A path that is already gone is skipped silently. Afterwards the sidecar records
leave the index and the list is invalidated. Files are removed outright (no trash); undo never brings them back.

`kinds`, `of_kind` and `counts` define the rail collections (Videos = has a video file, Audio = has an audio file, so a merged row is in both). `attach_local(rows, library_entries)` copies the download state onto playlist rows (`_dl` = `video`/`audio`/`both`/`""` plus the `_local_*` fields playback and the detail panel read); a row whose file is missing counts as not downloaded.
