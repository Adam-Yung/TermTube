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

## Measuring stability

`gh workflow run test.yml --ref <branch> -f repeat=10` runs the end-to-end check ten times per platform after a single install (about 8 minutes
per platform). A branch can only be dispatched once the workflow file exists on the default branch; the `repeat` input is read from the ref.

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

## Why a green run can be trusted

1. **Each end-to-end assertion was shown to fail when the behaviour breaks.** The app was broken on purpose five ways (seek disabled, pause
   disabled, history not recorded, stop not killing mpv, an import error at startup) and each was caught at the right step. One assertion that
   passed with seek disabled (the tone advanced on its own) was tightened.
2. **It runs the product, not a model of it.** Layer 3 uses the installed copy, its launcher, a real terminal (pty or ConPTY), real mpv and the
   app's own IPC. Nothing in that path is mocked.
3. **It found real bugs before any user did.** While being brought up on GitHub (Linux, macOS, Windows runners) it exposed:

| Found by | Bug | Platform |
|---|---|---|
| Designing layer 3 | The bundled-only dependency check rejected a distro mpv, so the app could not start (installer now links it) | Linux |
| `gate` | `thumbnail` and prefetch workers raised when their screen or app was gone (`WorkerFailed`, fatal in Textual) | all |
| `gate` | 73 `read_text()`/`open()` calls used the locale codec: non-ASCII titles broke data files outside `termtube.cmd` | Windows |
| `real app` | The installer's release lookup used the rate-limited GitHub API, then a fallback tag with no macOS asset | macOS (and shared networks) |
| `real app` | A Library file played with ytdl options and `--no-terminal` hid mpv's error: exit code 2, nothing on screen | Windows |
| `real app` | The audio launch thread swallowed its own exceptions: the bar stayed on "Buffering..." with nothing logged | all |
| `real app` (intermittent, 2 of 7 runs) | With `--debug`, the log panel's sink blocked while holding the logging lock and deadlocked against the UI thread: the app froze right after "Audio start". Reproduced with a test that hangs without the fix | all (it hit Windows) |
| e2e harness | `COLUMNS`/`LINES` inherited from a parent overrode the pty size (the app drew 80x24 with no action bar) | all |

4. **Flakiness is measured, not assumed.** Four green runs of one commit did not prove stability: the next run, on `main`, hit an intermittent deadlock. Treat a pipeline as stable only after many runs; the log below is the evidence.

## Run log

- 2026-11-16, branch `ci/platform-pipeline`, commit `a736451`: run 5 green on all six jobs (gate and real app on Linux, macOS and Windows), then three more full re-runs of the same commit, all green: 4 of 4 runs, 24 of 24 job executions.
- 2026-11-16, `main` at `f787344`: the first push to `main` failed `real app (windows-latest)` once, with the same freeze as run 4. That exposed the debug-log deadlock above; the earlier "4 of 4" had been luck. Fixed and re-verified below.
- 2026-11-16, commit `93b5fec` (debug-log deadlock fixed): dispatched with `repeat=10`, so one job per platform ran the end-to-end check ten times after one install. 10 of 10 passed on Linux, macOS and Windows (30 executions, 0 failures). The freeze had hit about one run in four on Windows before the fix, so ten clean runs per platform is strong evidence. Re-measure after any change to playback, logging or the installers: `gh workflow run test.yml -f repeat=10`.
- Before that, runs 1 to 4 were red for the reasons in the table above; every red run led to a product fix, none to a loosened assertion.

## Limits to keep in mind

- Windows and macOS runners are fresh virtual machines. A real user's machine has antivirus, other audio devices, a proxy, a different terminal.
- `real app` downloads deno, ffmpeg and mpv from GitHub releases. If an upstream asset disappears the job goes red, correctly: users would hit the
  same.
- `canary.yml` can only be dispatched once it is on the default branch (GitHub registers `workflow_dispatch` and schedules from there). Its script,
  `scripts/canary-live.py`, was run locally against live YouTube.
