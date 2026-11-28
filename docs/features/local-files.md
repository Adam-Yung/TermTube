# Local files

> Verified: 2026-11-28 · Sources: `src/local_files.py`, `src/local_media.py`, `src/tui/screens/mixins/local_tab.py`
> Serves: `library`, `playback`, `privacy`
> Owns: `src/local_files.py`, `src/local_media.py`, `src/tui/screens/mixins/local_tab.py`

## What it does

The **Local** tab (`F6`) lists the folder TermTube was started in (the home folder if that folder is gone) like a list of videos:

- a `..` row (except at a drive or filesystem root), then the folders, then the audio and video files, each sorted by name; hidden
  entries are left out; folder rows show the thumbnail placeholder. `Enter` on a folder opens it, `Backspace` goes up and lands on the folder just left. The path is the breadcrumb.
- A file row's title is its file name. On the highlighted row, `ffprobe` reads its length, streams (codec, size, frame rate, channels,
  sample rate), tags (title, artist, album, date, genre) and bit rate into the detail panel. The thumbnail is an image of the same name
  beside the file, else the embedded cover art, else a frame at 3 s (half way into a shorter file).
- Files play as audio (`a`) or video (`v`), queue (`e`), resume and enter History like any row; `p` adds them to a local playlist
  (the record keeps the path, so they play from History and playlists too). `f` filters, `m` marks. On a folder row `a` `v` `e` play the
  media files directly inside it; the `..` row only opens the parent.
- `D` deletes the file, or the marked files, for good after one `y` / `N`. Folders are never deleted; a symlink row removes the link,
  not its target; a file that changed since the list was read is left alone.
- `d`, `c`, `y`, `b`, `V` and `A` answer that a local file has no YouTube page or quality choice; the Enter menu and the Actions panel
  leave them out. Items added to a Library playlist keep their video or audio badge, or show the file as missing.

## Privacy

Nothing about a local file leaves the machine: its id (`local-…`, a hash) is refused by stream resolution, InnerTube, SponsorBlock and
the thumbnail download, and a local row without a path fails instead of reaching mpv's yt-dlp hook. Tests:
`src/tests/unit/test_local_privacy.py`, `src/tests/tui/test_local_tab.py`.

## Rules that must hold

- `ffmpeg` and `ffprobe` come only from the managed tools folder; without them rows have no details and no thumbnail.
- Only the highlighted row is probed; a listing reads one folder and never recurses.
- Paths reach mpv after `--` with `--access-references=no` (a file naming a URL inside is not followed) and ffmpeg as `file:` inputs;
  titles and probe text drop control characters. Names that do not encode as UTF-8 are not listed; `.ts` is listed only when it is
  MPEG-TS. Playing a local file never touches the Home suppression list.

## Limits

- Rows that were never highlighted show no length in the list.
- No toggle for hidden files and no recursive play.
- Images in a real terminal were not looked at; the frame and cover paths are tested against the real managed ffmpeg.

## How to check it

`src/tests/unit/test_local_files.py`, `src/tests/unit/test_local_delete.py`, `src/tests/unit/test_local_media.py`,
`src/tests/integration/test_local_media_real.py`, `src/tests/tui/test_local_tab.py`. Wiring: [../code/src/tui/screens/mixins/local_tab.py.md](../code/src/tui/screens/mixins/local_tab.py.md),
decision: [../decisions/local-files.md](../decisions/local-files.md).
