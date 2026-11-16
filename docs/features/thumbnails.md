# Thumbnails

Every video row shows a thumbnail in the detail panel, in one of three ways, chosen once at startup:

1. **Real image** through the terminal's graphics protocol (Kitty or Sixel; kitty, WezTerm, foot, iTerm2, Windows Terminal) using `textual-image`.
2. **Half-block colour art** (`▀` with a foreground and background colour: two pixel rows per cell) made with Pillow. Needs a 24-bit colour terminal.
   This is what every other terminal gets, and what tmux gets (pixel images flicker through tmux, so they are off there; `MYYOUTUBE_IMAGES=1` forces them on).
3. A **placeholder** when no image can be had (offline, removed video).

If your terminal reports no image support, a one-time dialog says so; "Never show again" sets `thumbnail_warning_dismissed`.

The `thumbnail_format` setting (Settings `,`): `auto` (default) uses a real image where the terminal supports it; `symbols` always uses half-block art, even in
a terminal with image support (useful if its graphics render badly). The change applies from the next thumbnail shown.

## How a thumbnail arrives

Pausing on a row starts a worker that resolves the image, in order: a copy already on disk, a thumbnail yt-dlp saved next to a download, then a
download from `i.ytimg.com` (the URL is derived from the video id when a row has none). The JPEG is validated, cached on disk, and rendered or
handed to the widget. Moving the cursor again discards a stale result; a screen closed meanwhile is ignored. Channel avatars load the same way.

Some networks (TLS-inspecting proxies) fail certificate checks for `i.ytimg.com`; the downloader retries without verification for these public images
only, and for nothing else.

Code: `src/ui/thumbnail.py`, `src/tui/thumb_loader.py`, `src/tui/widgets/thumbnail_widget.py`; decisions in `docs/decisions/thumbnails.md`.
