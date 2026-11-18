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
- `D` deletes files for good (no trash, `u` cannot undo it). On a row with both forms the bar asks `v video / a audio / b both / N cancel`
  with each size; with one form it asks `y / N`; with marked rows (`m`/`M`) it asks once: `Delete N items (X MB)?`. There is no "entry only"
  choice: it left the media on disk as an orphan. A row whose media is missing (sidecar left over) asks `Remove "<title>"?` and deletes the sidecar. Only the media, its `.info.json` and the thumbnail and
  subtitle files with the same name are removed, only inside `video_dir` / `audio_dir`, and never through a symlink or `..`.

- `a` and `v` play the local file directly (no YouTube request).
- The list refreshes by itself when files or folders appear (it compares the newest folder time in each tree, and a finished download refreshes it).
  Editing a sidecar in place is noticed on the next rebuild (the index compares each sidecar's modification time and size), which happens when
  a folder changes, a download completes or the app restarts.
- Playing a Library track records it in History like any other.

## Related files

`src/downloads.py`, `src/library.py`, `src/tui/screens/download_modal.py`, `download_picker_modal.py`; mirrors under `docs/code/`.

## Playlists

Local playlists live in `playlists.json` (v2: stable ids, items as slim snapshots with title, uploader, duration; see
[src/playlist.py](../code/src/playlist.py.md)). They hold references only: removing a video from a playlist or deleting a playlist never
deletes a downloaded file. On the Library tab (`F5`) playlists are entries of the left rail: `Tab` moves between the rail and the list, `j`/`k` walk the rail, `Enter` shows an entry
(`+ New playlist` asks for a name), `n` new, `R` rename, `D` on a rail entry deletes the playlist (one question, `u` undoes). In a playlist: `m`/`M` mark, `D` remove from the playlist, `J`/`K` reorder, `f` filter, `P` play, `S` shuffle, `E` queue the whole playlist as audio.
`p` on any video opens the playlist dialog: `Space` selects several playlists, `Enter` toggles them. Videos in a playlist are pinned in the
cache so the list and its thumbnails work offline. The first run on a v1 file keeps `playlists.json.v1` beside it.

## The Library tab and its rail

One tab holds everything downloaded or saved. The rail on the left lists `All downloads`, `Videos` (anything with a video file), `Audio` (anything with
an audio file; a video with a merged audio file is in both), then one entry per playlist, then `+ New playlist`. Counts sit beside each entry. Choosing an
entry loads it through the normal feed loader, so paging, filter, marks, `D` and `u` behave as everywhere else. Leaving the tab and coming back reopens the
last entry. Below 100 columns the rail is one line above the list (`Tab`, then `j`/`k`, `Enter`).

Playlist rows are checked against the Library index when they load: `⬇ video`, `⬇ audio`, `⬇ both` or `☁` (not downloaded). Playing a downloaded row uses the
file on disk, otherwise it streams. The detail panel lists "In playlists: A, B" for any video that is in one.

Filter (`f`) in the Library tab and in playlists takes free words (title, uploader or channel, tags, description) and tokens: `type:audio|video`,
`dur:<10m` / `dur:>20m`, `by:name` or `by:"two words"`, `year:2024`, `pl:name`, `dl:yes|no`. A malformed token is treated as a free word. Other tabs filter
plain text only. A search across History, Library and playlists together is not built.
