# Continuous integration: what a green run proves

The pipeline (`.github/workflows/test.yml`) exists so that **green on a platform means TermTube works there**, not just that tests passed. It has
three layers, each catching what the one before cannot.

| Layer | Job (runs on) | What it runs | What a pass proves |
|---|---|---|---|
| 1. Gate | `gate` (ubuntu, macos, windows) | `scripts/verify.sh`: byte-compile, ruff, about 390 unit and headless TUI tests, doc checks | The code is consistent, and its logic and layout work against mocks on this OS |
| 2. Real install | `real app` (ubuntu, macos; windows) | The real installer (`setup.sh --no-prompt`, `setup.ps1 -NoPrompt`), the installed launcher, `scripts/smoke-ipc.py` | The app installs from a clean runner: Python venv, deno, ffmpeg, mpv, the launcher; and a real mpv answers over the IPC socket (Unix) or named pipe (Windows) |
| 3. Real app | same jobs, last step | `scripts/e2e-local.py` against the **installed** copy, through the installed launcher | The app starts in a real terminal, renders, scans the library, starts and controls real mpv with real keys (play, pause, seek, stop), records history and quits with code 0 |

Layer 3 is hermetic: it needs no YouTube. It plays a generated tone from the Library and seeds the Home feed from the app's own cache, so it
cannot fail because YouTube is slow, blocks datacenter addresses or changes a page.

## What it deliberately does not prove

- **YouTube works.** Search, channels and stream resolution talk to a service we do not control. `scripts/canary-live.py` checks the live surface in a **separate** workflow (`canary.yml`, weekly and on demand) that is not a gate: red means "look at the parsers".
- **It looks right.** Thumbnails (no image protocol in CI), colours and layout are for a person on a real terminal.
- **Audio is heard.** Runners have no audio device; mpv runs with `ao=null`. The IPC and process control are real; the speaker is not.
- **Interactive installer choices.** The installers run with `--no-prompt` / `-NoPrompt`.

## Reading a run from the terminal

```
gh run list --limit 5
gh run view <run-id>                  # jobs and steps
gh run view <run-id> --log-failed     # only the failing steps' logs
gh run watch <run-id>                 # follow one live
```

## When a layer fails

- `gate`: reproduce with `scripts/verify.sh` (or the failing pytest). Windows runs it under Git Bash.
- `real app`, an install step: the installers download deno, ffmpeg and mpv from GitHub releases. A flaky download is retried three times; a persistent failure is a real problem with the installer or an upstream asset (`src/bootstrap.py`).
- `real app`, `smoke-ipc.py`: a step is printed as PASS or FAIL; mpv's stderr follows a failure. See `docs/code/scripts/smoke-ipc.py.md`.
- `real app`, `e2e-local.py`: each failed step is named and the last screen output is printed. See `docs/code/scripts/e2e-local.py.md` for what each step means. Run it locally with `scripts/e2e-local.py` (silent, isolated, about 10 s).

## Why these assertions can be trusted

Each end-to-end assertion was checked by breaking the app on purpose and watching it fail: seek disabled, pause disabled, history not recorded,
stop not killing mpv, an import error at startup. One assertion that passed with seek disabled (the tone advanced on its own) was tightened.
The pipeline's first design also found a real bug before running: on Linux the dependency check rejected a distro mpv, so the app could not start
(`docs/decisions/runtime-and-env.md`, 2026-11-16).
