# Downloads and the Library

## Downloading (`d`)

`d` on a video opens a picker: **video** or **audio**, then a quality. A progress dialog shows the transfer, then merging or conversion.

- **Video** is saved as mp4 (best video plus audio merged by ffmpeg) into `video_dir`; **audio** is converted to MP3 into `audio_dir`.
  File names follow `video_format` / `audio_format` (yt-dlp templates).
- Next to each file yt-dlp writes `<name>.info.json` (the video's metadata) and the thumbnail. The Library reads those. When a download finishes the
  thumbnail is converted to `<name>.jpg` (webp via PIL), the one new sidecar is indexed, and the video's metadata and thumbnail are pinned in the cache
  (the copy that pruning never deletes), so the Library works offline.
- **Esc cancels** the running download. The audio controls still work while the dialog is open: `Space` pauses and `x` stops background audio.
- Downloads never use your account cookies (the same reason as playback).
- Refused with a notice: **live streams** (no end), a row that is not a video, and a video the Library already holds as both video and audio.
  A video-only or audio-only local file still lets you download the other form.

## The Library tab (`F5`)

Lists everything found under `video_dir` and `audio_dir`: it scans for `.info.json` sidecars (including in subfolders), pairs each with the media file of the
same name, merges a video and its audio into one row, and sorts by upload date, newest first. A sidecar without a media file still shows a row marked
`⚠ file missing`; it cannot be played, only removed (`D`). Media without a sidecar is not listed.

- The Library keeps a slim index (`library.json` in the cache folder: title, channel, duration, date, views, first 500 characters of the description,
  tags, paths, sizes; never the format list). Only new or changed sidecars are read again, so a large Library opens quickly and the index stays small.
- The detail panel shows the file path (relative to the download folder) and the total size of the video and audio files.
- `D` deletes files for good (no trash, `u` cannot undo it). On a row with both forms the bar asks `v video / a audio / b both / e entry only / N cancel`
  with each size; with one form it asks `y / N`; with marked rows (`m`/`M`) it asks once: `Delete N items (X MB)?`. "Entry only" removes the
  `.info.json` and keeps the media (the row disappears because the Library lists sidecars). Only the media, its `.info.json` and the thumbnail and
  subtitle files with the same name are removed, only inside `video_dir` / `audio_dir`, and never through a symlink or `..`.

- `a` and `v` play the local file directly (no YouTube request).
- The list refreshes by itself when files or folders appear (it compares the newest folder time in each tree, and a finished download refreshes it).
  Editing a sidecar in place is noticed on the next rebuild (the index compares each sidecar's modification time and size), which happens when
  a folder changes, a download completes or the app restarts.
- Playing a Library track records it in History like any other.

## Related files

`src/downloads.py`, `src/library.py`, `src/tui/screens/download_modal.py`, `download_picker_modal.py`; mirrors under `docs/code/`.
