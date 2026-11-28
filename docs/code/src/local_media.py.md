# src/local_media.py

Details and thumbnails of local files for the Local tab, through the managed `ffprobe` and `ffmpeg` in `plat.get_deps_bin()`. A PATH copy
is never used (AGENTS.md); without the managed tools a row has no details and the thumbnail placeholder.

- **Callers.** `DetailFocusMixin._local_detail_worker` (`focus` group, highlighted row only) calls `details`; `ui/thumbnail.py`
  `_resolve_local_thumb` calls `thumbnail` from the `thumb` worker when no image of the same name sits beside the file. Both run on
  worker threads; each tool call has a timeout (10 s probe, 15 s frame), so a slow or network disk cannot hold a worker forever.
- **Probe cache.** In memory, 256 entries, keyed by the row id (which changes with size and mtime). Failures are not cached.
- **Thumbnail order.** Embedded cover art (`attached_pic` stream) first, then a frame at 3 s, or half way into a file of 3 s or less.
  Audio without art has no thumbnail. The JPEG goes to `<dest>.part` and is renamed, so a killed ffmpeg leaves no half image.
- **Hostile names.** Inputs and the output are passed as `file:<path>`: a name with a colon, a leading dash or a URL shape is still
  read as a file. No shell is involved. Every description line (tags, codec names) goes through `local_files.clean`, so an
  escape sequence in a tag never reaches the terminal.
