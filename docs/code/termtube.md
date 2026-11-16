# termtube

POSIX launcher (`bash`). Resolves symlinks to find its real directory, picks a Python, and `exec`s `src/main.py`. Windows equivalent: [termtube.cmd](termtube.cmd.md).

## Python lookup order

1. `.venv/bin/python3` beside the script (a checkout).
2. `~/.local/share/TermTube/.venv/bin/python3` (an installed copy); `SCRIPT_DIR` then points at the installed tree.
3. Neither found: run `scripts/setup.sh --no-prompt` from the checkout or the install, then use the installed venv.
4. No setup script: print instructions and exit 1.

## Notes

- `--uninstall` is handled here, before any Python is needed, so a broken venv cannot block removal. It runs `scripts/uninstall.sh` from the checkout or the install.
- The symlink loop matters: `~/.local/bin/termtube` is a symlink to the installed script, and `SCRIPT_DIR` must be the target's directory.
