# src/tui/widgets/thumbnail_widget.py

Shows one thumbnail with two backends, chosen once at import:

1. `textual_image` (kitty/sixel pixel image) when the terminal supports a real image protocol (`_HAS_TEXTUAL_IMAGE`). The widget receives a file path.
2. PIL half-block ANSI art, shown in the status `Static`, otherwise (see `src/ui/thumbnail.py`).

`pixel_images_enabled(config)` is true when `_HAS_TEXTUAL_IMAGE` and `thumbnail_format` is not `symbols`; the widget (per call, so Settings applies from the next thumbnail) and `src/tui/thumb_loader.py` both use it to decide which file to produce.

## Quirks

- `textual_image` queries the terminal (protocol, cell size) at import time. `src/main.py` imports `textual_image.widget` before Textual starts its I/O threads, and this module's import reuses it. Symptom of a late import: garbled output or a hang on startup.
- Pixel images are disabled inside tmux (kitty/sixel passthrough flickers). `MYYOUTUBE_IMAGES=1` forces them on. `textual_image` falling back to its Unicode renderer counts as "no image support", except on Windows Terminal (`WT_SESSION`).
- Every setter is keyed by id. `set_video_id` records the id the widget is allowed to show; `set_image_path`/`set_ansi` for another id are ignored. `set_loading` and `set_placeholder` are not keyed.
- The image widget and the status Static are mutually exclusive; `_show_status` hides the image.

See `docs/decisions/thumbnails.md`.

`MYYOUTUBE_IMAGES=1` is the only override for tmux.
