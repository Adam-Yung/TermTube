# src/config.py

The user's settings file, `~/.config/TermTube/config.yaml` (path from `plat.get_config_dir`). Decision: `docs/decisions/config.md`.

## Rules

- `Config.save()` is the only writer. It re-reads the file and merges, so keys this version does not know survive a save. Failures are
  logged and swallowed; a read-only config must not crash the UI.
- Defaults live in `DEFAULT_CONFIG`. On load, a file value replaces the default key by key. `cache_ttl` and `sponsorblock` merge one level
  deep so a partial override keeps the other defaults.
- A missing file is created on first construction.
- `insecure_thumbnails` is true only for a literal YAML `true`.
- `history_enabled` is false only for a literal `false`; `history_max` is an int clamped to 50..5000 (anything else reads as 500).
- Typed properties validate: unknown `theme` falls back to `crimson`, unknown `thumbnail_format` to `auto`, a non-list
  `sponsorblock.categories` to the default list. Raw access (`config["x"]`, `config.get`) does not validate.
- `cookies_file` from old configs is dropped on load. Auth now uses a browser only (see `docs/decisions/cookies-and-auth.md`).
- Callers change a setting with `config.set(key, value)` (memory only) and persist with `save()`, which returns False when nothing was written; nothing outside this module touches `_data`. `set`, `get` and `reset` take dotted keys for the two nested sections (`sponsorblock.enabled`, `cache_ttl.home`). The settings modal and the thumbnail warning dialog do this.
- `reload()` re-reads the file: it returns None and replaces every setting (defaults overlaid by the file, so a key deleted from the file reads as its default), or returns a one-line reason and leaves memory alone (unreadable file, YAML error, a file that is not a mapping, a missing file). `cache_ttl` and `sponsorblock` are updated in place, never rebound: `Cache` holds the same `cache_ttl` dict.

## Keys

`thumbnail_format` values: `auto` and `symbols`. Neither selects a renderer today: textual-image is used whenever it is installed and usable, else PIL half-block art (`docs/code/src/tui/widgets/thumbnail_widget.py.md`). Old configs with `sixel` or `ascii` read back as `auto`. `prefetch_video` is read through `prefetch_video_enabled` in
`src/tui/screens/mixins/detail_focus.py`. `thumbnail_warning_dismissed` is set by the thumbnail warning dialog.

`resolved_browser()` names the browser whose cookies are used (`auto` = first detected, None for `none` or nothing found). `rows_per_page` is an int clamped to 10..50 (anything else reads as 20); `VideoListPanel` latches it in `clear_and_set_loading`, so a change applies from the next list load. `prefetch_video_enabled` is true only for a literal `true`.

`browser_cookie_args()` turns `resolved_browser()` into `--cookies-from-browser <name>` for mpv's yt-dlp hook. `auto` picks the first detected
browser. `none` returns no flags.

## Known limits

- Tests that construct `Config` must pass `path=` to a tmp dir; the default path is the real user config.
