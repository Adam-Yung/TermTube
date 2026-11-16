# scripts/setup.ps1

Windows installer, counterpart of [setup.sh](setup.sh.md). Code goes to `%LOCALAPPDATA%\Programs\TermTube`, data to `%LOCALAPPDATA%\TermTube`, config to `%APPDATA%\TermTube`. The user `PATH` gets the app dir (where `termtube.cmd` lives). Decisions: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## Invariants

- **Deletion goes through `Remove-PathSafe`**, never `Remove-Item -Recurse -Force` on an install dir. On a junction, `-Recurse -Force` follows the link and deletes the target's contents. `Remove-PathSafe` detects the reparse point and removes only the link.
- `requirements.txt` is hashed (SHA256 in `<venv>\.requirements.sha256`) and pip is skipped when unchanged, same as `setup.sh`.
- The old `.venv` is moved to `%LOCALAPPDATA%\TermTube.venv.stash` before the app dir is wiped and restored afterwards, so reinstalling does not cost a 30 to 60 s pip run. If the move fails the venv is recreated.
- If the venv does not exist when dependencies are due, bootstrap is deferred (`$script:DeferBootstrap`) and run after venv creation.

## Legacy layout

Builds before 2026-05 put code directly in `%LOCALAPPDATA%\TermTube`, which is also the data dir (mpv, cache). `Install-Files` detects `src` or `termtube.cmd` there, stashes its `.venv`, removes only the code and launcher artifacts, and leaves the data in place. `uninstall.ps1` has the matching detection.

## Quirks

- `[Console]::OutputEncoding` is forced to UTF-8 so the box characters render; `termtube.cmd` sets `PYTHONUTF8=1` for the same reason at run time.
- The file starts with a UTF-8 BOM and uses CRLF, which Windows PowerShell 5.1 needs to read non-ASCII characters correctly. Keep both when editing.

## Limits

- The comment-based help still shows `-Sync` and `-Deps` examples and lists yt-dlp among the binary dependencies; neither the parameters nor the binary exist any more.
- Not run by tests; needs a manual run on Windows.
