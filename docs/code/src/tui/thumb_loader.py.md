# src/tui/thumb_loader.py

`load_thumbnail(app, target, vid, ...)`: the shared body of every thumbnail worker (main screen, channel screen, detail focus). The caller
owns the `@work(thread=True, exclusive=True, group="thumb")` wrapper and its session counter. This function owns the resolve and
delivery steps. Pipeline background: `docs/decisions/thumbnails.md`.

## Contract

- Runs in a worker thread. It delivers to `target` only through `app.call_from_thread`, so widget state changes happen on the UI thread.
- `is_current()` is polled after each slow step (download, render). A result for a row the cursor already left is dropped, not shown. The
  caller's session counter is what makes this true. The function holds no state about which row is current.
- `target` supplies `set_thumbnail_image(vid, path)`, `set_thumbnail_ansi(vid, ansi)` and `set_thumbnail_placeholder()`.
- With `textual-image` installed (`_HAS_TEXTUAL_IMAGE`) it delivers a validated JPEG path. Otherwise it delivers PIL half-block ANSI.
  Either failure delivers the placeholder.

## Cache

`_ansi_cache` is a 64-entry LRU of rendered ANSI keyed by `(vid, cols, rows)`, behind `_ansi_lock` (several workers touch it). It
saves the disk read when the cursor moves back over recent rows. The disk cache in `src/ui/thumbnail.py` sits behind it.
