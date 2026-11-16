# scripts/uninstall.ps1

Windows uninstaller. Removes the app dir, the legacy code dir (if it still holds code), the deps dir, and the `PATH` entries. `-Purge` also removes config, cache, logs and the data dir; `-Force` skips the prompt. Counterpart of [uninstall.sh](uninstall.sh.md).

## Invariants

- Removal is junction-aware (same reason as `Remove-PathSafe` in [setup.ps1](setup.ps1.md)): a sync-style install is a junction to a source repo, and recursing into it would delete the repo. Junctions are listed as `junction -> target` before the prompt.
- A legacy `%LOCALAPPDATA%\TermTube` is flagged only if it contains `src` or `termtube.cmd`. Without `-Purge`, only the code and launcher files in it are removed; mpv, cache and `history.json` stay.
- Both the current app dir and the historical bin dir are stripped from the user `PATH`.

## Limits

- File starts with `#Requires -Version 5.1`, uses CRLF. Not run by tests.
