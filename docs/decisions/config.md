# Config and install layout

Where files live, how sync mode links the install, and why shell UI tools were dropped.

## 2026-04-25 — Config at `~/.config/TermTube/config.yaml`

The path is XDG-compliant. The project root stays clean, with no user-specific files committed. Config in `~/.config/TermTube/` survives reinstalls and stays the same whether the user runs from the dev dir or from the installed copy at `~/.local/share/TermTube/`.

## 2026-04-25 — `--sync` creates a directory symlink, not file-by-file symlinks

`ln -s <orig_dir> <app_dir>` points the whole install path at the repo. The `.venv` created at `APP_DIR/.venv` then lives inside the repo dir and survives re-runs of `--sync`. File-by-file symlinks lose the venv on `rm -rf APP_DIR`, which setup.sh runs before re-linking.

On Windows the equivalent is a junction: see [setup.ps1 uses Remove-PathSafe](runtime-and-env.md#2026-05-16--setupps1-uses-remove-pathsafe-not-remove-item--recurse--force).

## 2026-04-25 — fzf and gum deprecated

Both tools need shell subprocess spawning and do not fit Textual's reactive widget model. All UI is native Textual widgets, which gives proper focus management, async data binding and consistent theming.

## 2026-11-17 — One JsonStore for user JSON files

`src/store.py` owns load, versioned envelope (`{"version", "data"}`), atomic 0600 write, corrupt-file `.bad` copies and locking. Playlists moved onto it
unchanged in shape (v1); the file gains the envelope, so a build older than this one reads it as a playlist named `version`. Phase 5 migrates the data shape. Deferred (debounced) saves exist for history so the UI thread never waits on the disk; `atexit` flushes.

## 2026-11-18 — Settings covers the config file; refusals explain; reset is Backspace

Settings is one list of sections driven by a `Field` table (`src/tui/settings_fields.py`), not one `ListView` per setting. Typed values are validated before they are written and a bad one stays in the open field with a one-line reason; the old silent fallbacks (`theme`, `thumbnail_format`) remain only for hand-edited YAML. Name templates reuse `downloads.check_template`, the guard the download path applies, instead of a second copy.

Reset to default is `Backspace` on the row, because `d` is the download key in every list. A text field keeps Backspace for itself. Destructive actions (clear cache, watch history, search history) need a second `Enter` on the same row; moving the cursor cancels. The modal has no undo for them, as with `--clear-history`.

`Config.reload()` replaces every setting with defaults overlaid by the file, so a key deleted from the file reads as its default, and it mutates `cache_ttl` and `sponsorblock` in place because `Cache` holds the `cache_ttl` dict. A file that fails to parse changes nothing in memory. `rows_per_page` is latched by `VideoListPanel.clear_and_set_loading`, so a change applies at the next list load and never re-pages a list the user is looking at. `cache_ttl.subscriptions` gets no row: nothing reads it.
