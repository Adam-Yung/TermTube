# scripts/uninstall.sh

Removes the app dir, the `~/.local/bin/termtube` symlink and `~/.local/termtube-deps`. With `--purge` also config, cache and logs. Reached through `termtube --uninstall` or directly. Windows counterpart: [uninstall.ps1](uninstall.ps1.md).

## Invariants

- Without `--purge`, `~/.config/TermTube` (config, history, cookies setting) and the cache survive; the summary says so.
- `remove_item` removes a symlink as a link (`rm -f`), never recursing into its target.
- Lists everything it will delete and asks `[y/N]` first; `--force` skips the prompt.

## Limits

- It stops running processes with `pkill -f "$APP_DIR/"`: only commands started from the installed app directory. A copy run from a git checkout is not stopped.
- It removes `termtube-mpv*.sock` from `$XDG_RUNTIME_DIR` or `/tmp/termtube-<uid>/` (the directory `plat._unix_ipc_dir` uses, [src/plat.py](../src/plat.py.md)) and removes that directory if empty.
- The unix script was only syntax-checked (`bash -n`); it was not run.
- Not run by tests.
