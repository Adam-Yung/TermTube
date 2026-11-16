# termtube.cmd

Windows launcher, equivalent of [termtube](termtube.md). Same four-step lookup: `.venv\Scripts\python.exe` beside the script, then `%LOCALAPPDATA%\Programs\TermTube`, then run `scripts\setup.ps1 -NoPrompt`, then fail.

- Sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. Without them, Windows consoles on cp1252 crash on the TUI's non-ASCII output.
- `--uninstall` runs `scripts\uninstall.ps1` from the checkout or the install dir before looking for Python.
- `setup.ps1` puts the install dir on the user `PATH`, which is how `termtube` resolves to this file.
- CRLF line endings are required for `goto` labels in batch files; keep them.
