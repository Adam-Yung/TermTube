# scripts/setup-shortcut.sh

The last, optional step of [setup.sh](setup.sh.md): `install_shortcut` asks, then writes a Linux `.desktop` entry or `~/Applications/TermTube.app`. A separate file so each stays readable.

## Contract

- Sourced by `setup.sh` through `${ORIG_DIR}/scripts/`, never run on its own. It uses `setup.sh`'s `INTERACTIVE`, `APP_DIR`, `BIN_DIR` and print helpers.
- It ships with `scripts/`, which a full install and `--refresh` copy whole, so the installed `setup.sh` finds it too.
- `--no-prompt` returns without writing anything.
- The macOS bundle's executable only hands off to [launch-macos.sh](launch-macos.sh.md); the Linux entry and the bundle use absolute paths, because a desktop session's `PATH` often lacks `~/.local/bin`.

## Limits

- No test reaches it: CI installs with `--no-prompt`.
