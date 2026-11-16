# Config and install layout

Where files live, how sync mode links the install, and why shell UI tools were dropped.

## 2026-04-25 — Config at `~/.config/TermTube/config.yaml`

The path is XDG-compliant. The project root stays clean, with no user-specific files committed. Config in `~/.config/TermTube/` survives reinstalls and stays the same whether the user runs from the dev dir or from the installed copy at `~/.local/share/TermTube/`.

## 2026-04-25 — `--sync` creates a directory symlink, not file-by-file symlinks

`ln -s <orig_dir> <app_dir>` points the whole install path at the repo. The `.venv` created at `APP_DIR/.venv` then lives inside the repo dir and survives re-runs of `--sync`. File-by-file symlinks lose the venv on `rm -rf APP_DIR`, which setup.sh runs before re-linking.

On Windows the equivalent is a junction: see [setup.ps1 uses Remove-PathSafe](runtime-and-env.md#2026-05-16--setupps1-uses-remove-pathsafe-not-remove-item--recurse--force).

## 2026-04-25 — fzf and gum deprecated

Both tools need shell subprocess spawning and do not fit Textual's reactive widget model. All UI is native Textual widgets, which gives proper focus management, async data binding and consistent theming.
