# src/ui/thumbnail.py

Everything about thumbnail files, with no Textual dependency: find or download a JPEG, validate it, render PIL half-block ANSI art for
terminals where `textual-image` is unavailable. Callers: `src/tui/thumb_loader.py` (worker threads), `src/ytdlp.py` (`_best_thumb_url`),
`src/tui/app.py` (pruning). Decisions: `docs/decisions/thumbnails.md`.

## Rendering paths

1. `textual-image` (Kitty or Sixel) draws the cached JPEG. This module only supplies and validates the file.
2. `render_pil_halfblock`: one terminal cell is two pixel rows (`▀` with foreground = top pixel, background = bottom pixel). Needs a
   24-bit color terminal.
3. Placeholder text, when no image can be had.

## Files and caches

- JPEGs: `THUMB_DIR/<video_id>.jpg`, shared with `Cache`. `ensure_thumb_jpeg` resolves in order: disk, a thumbnail yt-dlp wrote next to a
  downloaded file (library entries; copied into the cache), then network via `plat.download_thumbnail`. A failed download deletes the
  partial file so it is not mistaken for a hit.
- Rendered art: `CACHE_DIR/rendered/<id>_<cols>x<rows>_pil.ansi`, so a re-render at the same panel size is a file read. Pruned by
  `prune_old_rendered` (age, then count) from housekeeping.
- `validate_thumb` fully decodes the image. An HTML error page saved as `.jpg` otherwise reaches `textual-image` and renders as garbage.
- Channel avatars pass `url=` and use the channel id as `video_id`; the cache path is shared with video ids.

## Threading

`ensure_thumb_jpeg`, `download` and `render_pil_halfblock` block on disk and network. Call them from a worker thread only. Nothing here
takes a lock; two workers racing on the same id both download, and the last `write` wins with identical content.

## `best_thumb_url` and the id-derived fallback

Order: the extractor's `thumbnail`, the last JPG in `thumbnails`, then `https://i.ytimg.com/vi/<id>/mqdefault.jpg` built from an
11-character video id. The last rung needs no yt-dlp or InnerTube call, so rows that carry only an id (history, playlists, queue) get a
thumbnail. Channel rows (`_is_channel`) and placeholder ids (`__playlist__…`) never match. The CDN returns a generic grey image, not a
404, for a deleted video; `validate_thumb` accepts it. Optimization plan step 1: `docs/plans/2026-11-15-optimization-PLAN.md`.
