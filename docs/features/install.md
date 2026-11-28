# Install, update, uninstall

> Verified: 2026-11-28 · Sources: `scripts/setup.sh`, `scripts/setup.ps1`, `src/bootstrap.py`, `src/release_download.py`, `src/updater.py`, `src/plat.py`, `src/deps.py`, `termtube`
> Serves: `install`
> Owns: `src/bootstrap.py`, `src/release_download.py`, `src/updater.py`, `src/deps.py`, `src/plat.py`, `scripts/setup*.sh`, `scripts/setup.ps1`, `scripts/uninstall.*`, `scripts/launch-macos.sh`, `termtube`, `termtube.cmd`

## What it does

Installs TermTube on macOS, Linux and Windows with its own venv and managed Deno, ffmpeg and mpv; updates and removes it. The steps a person
follows are in [../guides/setup.md](../guides/setup.md).

## How it works

`scripts/setup.sh` or `scripts/setup.ps1` copies the code, builds the venv and runs `python -m src.bootstrap`, which downloads the tools into
`termtube-deps/bin` (Linux links the distribution's mpv). `termtube` / `termtube.cmd` find the venv and start `src/main.py`, which checks the
tools (`src/deps.py`). `termtube --update` runs `src/updater.py`: tools, yt-dlp, app code. `src/plat.py` holds every per-OS path and call.

## Code

`src/bootstrap.py`, `src/release_download.py`, `src/updater.py`, `src/deps.py`, `src/plat.py`, `scripts/setup.sh`, `scripts/setup-shortcut.sh`,
`scripts/setup.ps1`, `scripts/uninstall.sh`, `scripts/uninstall.ps1`, `scripts/launch-macos.sh`, `termtube`, `termtube.cmd`.

## Rules that must hold

- Only the managed bin folder satisfies the dependency check; system copies never do.
- A `dev` install is never overwritten by the updater. Nothing updates in the background.
- An interrupted download never replaces a working binary.
- Uninstall keeps config, history, cache and downloads unless asked to purge; downloads are never removed.

## Limits

- Downloads are not checksum or signature verified.
- Interactive installer prompts and the desktop shortcut are checked by hand only.

## How to check it

`src/tests/unit/test_bootstrap_install.py`, `src/tests/unit/test_setup_refresh.py`, `src/tests/unit/test_updater.py`, and the `real app`
pipeline jobs ([../guides/ci.md](../guides/ci.md)).
