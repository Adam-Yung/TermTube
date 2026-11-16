# Continuous integration

`.github/workflows/test.yml` runs on every push and pull request. Three jobs:

| Job | Runner | What it checks |
|---|---|---|
| `verify` | ubuntu-latest, Python 3.12 | `scripts/verify.sh`: byte-compile, ruff, all tests, doc mirrors, doc links, dead code |
| `platforms` | macos-latest and windows-latest | The same gate. Windows runs it under Git Bash (`shell: bash`); `verify.sh` finds `.venv/Scripts/python.exe` or plain `python` there |
| `windows-install` | windows-latest | The real installer and launcher: `scripts\setup.ps1 -NoPrompt` under Windows PowerShell 5.1 (parses the script, builds the venv, downloads deno, ffmpeg and mpv from GitHub releases through `src/bootstrap.py`), lists the installed layout, runs `termtube.cmd --version`, then `scripts\smoke-ipc.py --require-mpv` with the installed venv: real mpv over the named pipe and pywin32 |

What CI cannot cover: the interactive TUI on Windows Terminal (keys, colours, thumbnails), real audio output, and a machine with an antivirus. The
runner has no audio device; the smoke script uses `--ao=null` so that does not matter.

## Reading a run from the terminal

```
gh run list --limit 5
gh run view <run-id>                  # jobs and steps
gh run view <run-id> --log-failed     # only the failing steps' logs
gh run watch <run-id>                 # follow one live
```

## When `windows-install` fails

The step that failed says which layer: `setup.ps1` (syntax, Python lookup, pip, bootstrap download), `termtube.cmd` (venv path, `src\main.py`),
or `smoke-ipc.py` (mpv missing from `%LOCALAPPDATA%\termtube-deps\bin`, pywin32, the pipe). `scripts/smoke-ipc.py` prints each step as PASS or FAIL
and mpv's stderr on failure; `docs/code/scripts/smoke-ipc.py.md` lists what the steps mean.
