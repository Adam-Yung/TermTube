# src/tui/settings_fields.py

The table behind the Settings screen: one `Field` per setting (key, label, kind, section, how to read it, how to validate typed text). `SettingsModal` renders and edits whatever is in `FIELDS`; adding a setting means adding a row here, a typed accessor in `Config`, and a line in `docs/features/configuration.md`.

## Rules

- `key` is a `Config` key; `section.name` (`sponsorblock.enabled`, `cache_ttl.home`) reaches into the two nested sections through `Config.get/set/reset`.
- `kind` drives the modal: `bool` toggles, `choice` opens `QualityModal` as a picker, `text` and `int` open the inline input, `action` runs a command (clear, reload), `info` is a read-only line the cursor skips.
- Every `parse` raises `Refused` with a one-line reason; the modal shows it and keeps the old value. Nothing falls back silently.
- The download name templates use `downloads.check_template`, the same guard `_outtmpl` applies at download time, so Settings and the download path cannot disagree.
- `parse_dir` accepts an existing writable directory, or a path whose nearest existing parent is a writable directory (`downloads.py` creates the rest). It does not create anything itself.
- Value ranges (`rows_per_page` 10..50, `history_max` 50..5000) mirror the clamps in `Config`; a value typed outside them is refused, a value hand-edited into the YAML is clamped on read.
- Cache TTLs accept 60 s to 30 days. `cache_ttl.subscriptions` has no row: nothing reads it yet (see `docs/features/configuration.md`).
- `browser_status` is the Account section's "In use" line; it asks `Config.resolved_browser`, the same resolver mpv's cookie flags use.
