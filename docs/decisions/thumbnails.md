# Thumbnails

Image rendering paths, chafa settings, and the detail panel's thumbnail interface.

## 2026-04-25 — `textual-image` with chafa fallback

`textual-image` gives native Sixel (tmux, iTerm2, WezTerm) and Kitty graphics protocol support, which render at full image quality. Terminals without those protocols fall back to `chafa`, which generates ANSI block and Unicode sextant art. Together they cover effectively every terminal environment.

## 2026-05-03 — Chafa flags and render cache (HomeScreen v2)

Chafa flags moved from `--optimize=3 --color-space=din99d` to `--optimize=1`. The perceptual colour-space matrix conversion was the most expensive part and made no visible difference on thumbnails.

Output is cached under `~/.cache/termtube/chafa/<vid>_<cols>x<rows>_<fmt>.ansi`, so re-rendering at the same panel size is free.

The `thumb` worker that runs chafa is described in [HomeScreen v2 worker topology](concurrency.md#2026-05-03--homescreen-v2-worker-topology).

## 2026-05-03 — DetailPanel as a passive view (HomeScreen v2)

DetailPanel became a passive view. The screen calls `update_basic`, `set_thumbnail_loading`, `set_thumbnail_image`, `set_thumbnail_ansi`, `set_thumbnail_placeholder` and `refresh_metadata`. On resize or screen resume, the panel posts a `RerenderRequested` message, and the screen handles it by re-kicking the thumb worker.

## 2026-11-16 — `thumbnail_format: symbols` forces half-block art

The setting had a picker and no effect. `pixel_images_enabled(config)` (`thumbnail_widget.py`) is now the one test: the terminal can show pixel images **and** the setting is not `symbols`. The widget and `thumb_loader.load_thumbnail` both ask it, so a capable terminal can be pinned to half-block art (for example when its graphics protocol renders badly). The widget still composes the pixel widget on capable terminals so the choice applies live, from the next thumbnail on; `set_ansi` hides the pixel widget. `auto` keeps detection as before.

## 2026-11-17 — Unverified TLS for thumbnails is opt-in

The downloader used to retry every certificate failure without verification. That silently accepted any intercepting party for every machine. The retry now needs `insecure_thumbnails: true` (default off); without it the row keeps the placeholder. The same change caps a download at 2 MB, accepts only http(s) URLs (a `file://` thumbnail URL in an entry would otherwise copy a local file into the cache) and decodes the file with PIL before it enters the cache, so a captive-portal HTML page no longer sits there as a "thumbnail".
