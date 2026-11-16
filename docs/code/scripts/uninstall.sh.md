# scripts/uninstall.sh

Removes the app dir, the `~/.local/bin/termtube` symlink and `~/.local/termtube-deps`. With `--purge` also config, cache and logs. Reached through `termtube --uninstall` or directly. Windows counterpart: [uninstall.ps1](uninstall.ps1.md).

## Invariants

- Without `--purge`, `~/.config/TermTube` (config, history, cookies setting) and the cache survive; the summary says so.
- `remove_item` removes a symlink as a link (`rm -f`), never recursing into its target.
- Lists everything it will delete and asks `[y/N]` first; `--force` skips the prompt.

## Limits

- It stops running processes with `pkill -f termtube`, which can match unrelated processes whose command line contains that word.
- It removes `/tmp/termtube-mpv.sock`, an older socket location. Current sockets live under `$XDG_RUNTIME_DIR` or `/tmp/termtube-<uid>/` ([src/plat.py](../src/plat.py.md)); the latter is not cleaned.
- Not run by tests.
