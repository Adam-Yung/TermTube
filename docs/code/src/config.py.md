# src/config.py

The user's settings file, `~/.config/TermTube/config.yaml` (path from `plat.get_config_dir`). Decision: `docs/decisions/config.md`.

## Rules

- `Config.save()` is the only writer. It re-reads the file and merges, so keys this version does not know survive a save. Failures are
  logged and swallowed; a read-only config must not crash the UI.
- Defaults live in `DEFAULT_CONFIG`. On load, a file value replaces the default key by key. `cache_ttl` and `sponsorblock` merge one level
  deep so a partial override keeps the other defaults.
- A missing file is created on first construction.
- Typed properties validate: unknown `theme` falls back to `crimson`, unknown `thumbnail_format` to `auto`, a non-list
  `sponsorblock.categories` to the default list. Raw access (`config["x"]`, `config.get`) does not validate.
- `cookies_file` from old configs is dropped on load. Auth now uses a browser only (see `docs/decisions/cookies-and-auth.md`).
- The settings modal writes `config._data[...]` directly, then calls `save()`.

## Keys

`thumbnail_format` values: `auto` and `symbols` both mean PIL half-block art. `sixel` and `ascii` are accepted but have no separate
renderer; textual-image takes over whenever it is installed. `prefetch_video` is read with `config.get` in
`src/tui/screens/mixins/detail_focus.py` and has no UI. `thumbnail_warning_dismissed` is set by the thumbnail warning dialog.

`browser_cookie_args()` turns `browser` into `--cookies-from-browser <name>` for mpv's yt-dlp hook. `auto` picks the first detected
browser. `none` returns no flags.

## Known limits

- Tests that construct `Config` must pass `path=` to a tmp dir; the default path is the real user config.
