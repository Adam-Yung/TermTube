# Active Context

## Last completed task (2026-04-25)

Completed a setup/config cleanup pass:

1. **Fixed `--sync` symlink in `setup.sh`** — was using broken `ln -sf ORIG_DIR "$(dirname APP_DIR)"`. Now correctly does `rm -rf APP_DIR && ln -s ORIG_DIR APP_DIR`, making the install path a single directory symlink. `.venv` lives inside the repo and survives re-runs.

2. **Removed conda/mamba** from `setup.sh`, `termtube` launcher, and `uninstall.sh`. All environment management is now Python `venv` only.

3. **Added `--help` to `setup.sh`** with full option docs, config paths, and dependency hints.

4. **Moved config to `~/.config/TermTube/`** — `config.py` now uses `~/.config/TermTube/config.yaml` as the sole config path. Removed the project-root `TermTube.yaml` fallback. Updated cookies path references in `deps.py`. Moved the existing `TermTube.yaml` to `~/.config/TermTube/config.yaml`.

5. **Updated README, CLAUDE.md** with correct paths, venv-only install docs, and setup mode docs.

6. **Created `memory/` folder** with `architecture_decisions.md` and this file.

## No active in-progress work.
