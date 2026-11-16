# src/library.py

Data for the Library page: scans `video_dir` and `audio_dir` for the `.info.json` sidecars yt-dlp writes next to each download. Callers:
the library feed loader (`all_entries`) and the download modal (`invalidate_cache` after a download completes).

## How entries are built

- One recursive walk per directory collects sidecars and media files, keyed by file stem. A sidecar `Title.info.json` pairs with the media
  file whose stem is `Title`. Images and `.json` files are not media.
- The entry is the sidecar's JSON plus `_local_path`, `_local_type` (`video` by extension, else `audio`) and `_sidecar_path`. A sidecar
  with no media file still yields an entry without `_local_path`.
- The same video id in both directories yields one entry, taken from the video directory, with `_has_audio` and `_audio_path` added.
- Sorted by `upload_date` descending (yt-dlp `YYYYMMDD` strings compare correctly as text). Entries without a date sort last.

## Cache

`all_entries` caches per `(video_dir, audio_dir)`. A cached list is returned while both directories' mtimes are unchanged. Creating or
deleting a file in a directory bumps that directory's mtime on common filesystems, so the check costs two `stat` calls.

Limit: mtime only reflects a directory's direct children. A file added in a subfolder (`rglob` descends into them) does not bump the
top-level mtime, so it appears only after `invalidate_cache()`. The download modal calls it after each download.

`_lock` serializes scans, so a second caller waits for the first scan instead of repeating it. A scan walks the whole tree on the
calling thread; call from a worker.
