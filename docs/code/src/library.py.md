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

`all_entries` caches per `(video_dir, audio_dir)`. A cached list is returned while the newest mtime in each tree is unchanged. `_dir_mtime`
walks the directory and every subdirectory (directories only, not files): adding a file bumps its folder, adding a folder bumps its
parent, so the check is one `stat` and one `scandir` per directory in the tree.

Limit: editing a sidecar in place does not change any directory mtime, so it shows up only after `invalidate_cache()` (the download modal
calls it after each download). A filesystem with coarse timestamps can miss two changes within one tick.

`_lock` serializes scans, so a second caller waits for the first scan instead of repeating it. A scan walks the whole tree on the
calling thread; call from a worker.
