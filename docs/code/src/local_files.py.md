# src/local_files.py

The Local tab's view of the disk: the launch folder, one folder's listing as rows, the tracks of a folder row, and deleting one file.
Plain module, no state but the launch folder. Decision: [../../decisions/local-files.md](../../decisions/local-files.md).

- **Launch folder.** `capture_launch_dir` is the first call in `main.main()`, before argument parsing or any import that could change the
  working directory; neither launcher (`termtube`, `termtube.cmd`) changes it. A working directory that no longer exists falls back to
  the home folder. Tests set `_launch_dir` to an empty temp folder (root `conftest.py`).
- **Ids.** File rows: `local-` + 20 hex of a SHA-1 over absolute path, size and mtime (ns). The id keys every cache (thumbnail JPEG,
  rendered ANSI, probe results), so a changed file is read again. `is_local_id` is the one test the network modules use to refuse an
  id (`streams`, `innertube.fetch_video_details`, `sponsorblock`, `ui/thumbnail.download`, the mpv yt-dlp fallback in `audio_launch`
  and `watch_modal`). Folder rows: `__dir__` + a path hash; the `__` prefix makes the detail focus and thumbnail code skip them.
- **Listing.** One `os.scandir`, never recursive. `is_dir()`/`is_file()` follow symlinks, so a link to a folder is a folder row and a
  loop is only a row. Dot names, (Windows) the hidden attribute and names that do not encode as UTF-8 (Linux surrogates) are skipped; `.ts` is listed only when it is MPEG-TS (sync byte `0x47` at offsets 0 and 188, 189 bytes read), not TypeScript; an entry whose stat fails is skipped; a folder that
  cannot be opened gives `Listing.error` and only the `..` row. `cancelled` is polled per entry. The `..` row carries `_is_parent`. `clean` (titles and probe text) replaces non-printable
  characters (newlines, escapes, undecodable bytes) with spaces; `_local_path` keeps the raw name.
- **Delete.** `delete_file` unlinks only a regular file or a symlink (`os.unlink` never follows, so a link's target stays), and only
  when size and mtime still equal the listing's. Folders and rows that are not local files are refused with a reason.
