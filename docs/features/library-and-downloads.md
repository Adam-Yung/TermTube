# Downloads and the Library

## Downloading (`d`)

`d` on a video opens a picker: **video** or **audio**, then a quality. A progress dialog shows the transfer, then merging or conversion.

- **Video** is saved as mp4 (best video plus audio merged by ffmpeg) into `video_dir`; **audio** is converted to MP3 into `audio_dir`.
  File names follow `video_format` / `audio_format` (yt-dlp templates).
- Next to each file yt-dlp writes `<name>.info.json` (the video's metadata) and the thumbnail. The Library reads those.
- **Esc cancels** the running download. The audio controls still work while the dialog is open: `Space` pauses and `x` stops background audio.
- Downloads never use your account cookies (the same reason as playback).
- Refused with a notice: **live streams** (no end), a row that is not a video, and a video the Library already holds as both video and audio.
  A video-only or audio-only local file still lets you download the other form.

## The Library tab (`F5`)

Lists everything found under `video_dir` and `audio_dir`: it scans for `.info.json` sidecars (including in subfolders), pairs each with the media file of the
same name, merges a video and its audio into one row, and sorts by upload date, newest first. A sidecar without a media file still shows a row.

- `a` and `v` play the local file directly (no YouTube request).
- The list refreshes by itself when files or folders appear (it compares the newest folder time in each tree, and a finished download refreshes it).
  Editing a sidecar in place is not noticed until a download completes or the app restarts.
- Playing a Library track records it in History like any other.

## Related files

`src/downloads.py`, `src/library.py`, `src/tui/screens/download_modal.py`, `download_picker_modal.py`; mirrors under `docs/code/`.
