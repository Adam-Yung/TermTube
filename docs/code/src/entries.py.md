# src/entries.py

`TypedDict`s for the row dicts that move from loaders to the list, the detail panel, the action bar and the audio queue: `VideoEntry`, `LibraryEntry` (a video plus the `_local_*` and sidecar keys), `ChannelEntry`, `PlaylistEntry`, and `Entry`, the union of them. Used in annotations only; rows are still plain dicts, so there is no runtime cost and no validation.

## Invariants

- Every key is optional (`total=False`): each source fills a different subset (search has no `upload_date`, channel browse has no exact date, yt-dlp has most of both).
- The shared base `_Row` carries the keys any row kind may be asked for (`id`, `title`, `thumbnail`, the `_is_playlist` / `_is_channel` flags), so `entry.get("_is_channel")` is valid on the union.
- `src/tests/unit/test_entries.py` parses the InnerTube search, channel and playlist fixtures and asserts every emitted key is declared here. Add a key to the type in the same change that adds it to a parser.

## Limits

Keys that exist only on one kind (for example `duration`) are read through `.get` on the union by the list widgets; a strict type checker would flag that. No checker runs in the gate. Fields yt-dlp adds that the UI never reads (formats, subtitles) are not listed.
