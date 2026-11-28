# Decisions: the Local tab

## 2026-11-28 — A Local tab on the main screen, one folder at a time

Owner request: a tab that lists the media files of the launch folder as video rows (file name as title, a frame or cover as thumbnail,
probed details) and its folders as rows to open, so TermTube plays local files like a terminal VLC. Owner answers: navigating above the
launch folder is allowed (a `..` row and Backspace); `D` deletes a file for good after one y/N; the tab is `F6`, Help moves to `F7`.

Approaches considered:

1. **A view of `MainScreen` (picked).** `local` is one more tab id; its loader lists one folder on the `feed_loader` thread; files are
   ordinary rows with `_local_path` (the Library's playback path already plays those without yt-dlp), folders are placeholder rows
   (`__dir__…` ids, so the detail focus and thumbnail code skip them on their own). Reuses the list, filter, marks, `D` (`Removal`),
   detail panel, queue, history, playlists and the playlist-row `a` `v` `e` handlers. Risk: every place that turns an id into a
   YouTube request must refuse local ids; guarded at the network boundary (streams, InnerTube details, SponsorBlock, thumbnail
   download, the mpv yt-dlp fallback) and covered by tests.
2. **A pushed `LocalScreen` like `ChannelScreen`.** A clean separation, but it duplicates the screen wiring (mixins, bindings, layout
   audit) for a list that behaves like the main list, and a tab key cannot reach a pushed screen.
3. **Folders as Library rail entries.** The rail is for collections of downloads; folder trees do not fit a flat rail, and the Library's
   delete rules (inside the download roots only) are the opposite of what Local needs.

Details settled with it:

- **Ids.** A file row's id is `local-` plus a hash of its absolute path, size and mtime: thumbnails, rendered thumbnails and probe
  results are cached by id, so a changed file is read again. Resume and history follow the id; a rewritten file starts from zero.
- **Non-recursive.** A listing reads one folder; `a` `v` `e` on a folder row play the media directly inside it. No walk, so no
  symlink loop can hang it. Hidden entries (dot names, the Windows hidden attribute) are left out.
- **Probe on focus.** `ffprobe` runs for the highlighted row only (the `focus` worker, after the dwell), never for the whole folder;
  the thumbnail worker uses an image of the same name beside the file, then embedded cover art, then a frame at 3 s (half the
  length for shorter files). Both use the managed `ffmpeg`/`ffprobe` only; without them the row has no details and a placeholder.
- **Hostile names.** Files reach mpv after `--` as absolute paths and ffmpeg as `file:` URLs; titles drop control characters and
  are escaped as markup like every other title.
- **Delete.** Only a regular file or a symlink (the link, never its target), never a folder, and only when its size and mtime still
  match the listing.
- **Seven tabs fit.** Tab padding drops from 3 to 2 cells a side, and under 100 columns to one cell after the label, so the
  bar fits 100 and 80 columns (the layout audit fails on a protruding tab bar).
- **Not in the first cut:** durations of rows that were never highlighted, recursive play, a toggle for hidden files.
