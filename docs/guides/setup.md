# Setup guide: install, run, develop, update, move, uninstall

> Verified: 2026-11-28 · Sources: `scripts/setup.sh`, `scripts/setup.ps1`, `scripts/uninstall.sh`, `scripts/verify.sh`, `scripts/dev-setup.sh`, `src/main.py`, `src/updater.py`, `src/plat.py`

For people and for agents. The short version is in the [README](../../README.md); this is the complete one. Two environments exist and must not be
confused: the **installed app** (what a user runs) and the **checkout** (where you develop). [environments.md](environments.md) explains the split.

Contents: [Requirements](#requirements) · [Install](#install) · [First launch](#first-launch) · [Update](#update) ·
[Uninstall and reinstall on another machine](#uninstall-and-reinstall-on-another-machine) · [Develop](#develop) · [Test](#test) ·
[Environment variables and files](#environment-variables-and-files) · [Troubleshooting](#troubleshooting) · [For agents](#for-agents)

---

## Requirements

| Need | Version | Notes |
|---|---|---|
| Python | 3.11 or newer | The installer finds `python3.13`, `3.12`, `3.11`, then `python3`. |
| git | any | Only to clone. |
| Network | `github.com`, PyPI, `www.youtube.com` | Setup downloads tools from GitHub releases and packages from PyPI; the app talks to YouTube. |
| mpv | **Linux only: install it yourself first** | `sudo apt install mpv` / `dnf install mpv` / `pacman -S mpv`. There is no static Linux build to download. |
| A terminal with 24-bit colour | | For half-block thumbnails. Kitty or Sixel support gives real images. |

macOS and Windows need nothing else: Deno, ffmpeg and mpv are downloaded for you (and a headless `mpv.exe` on Windows).

## Install

### macOS and Linux

```bash
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/termtube
cd ~/termtube
bash scripts/setup.sh              # add --no-prompt for a non-interactive install
```

What `setup.sh` does, in order: finds Python 3.11+; copies `src/`, `scripts/`, `assets/` and the launcher to `~/.local/share/TermTube/`;
builds `~/.local/share/TermTube/.venv` and installs `requirements.txt` (skipped when its hash matches the one stored in the venv); downloads Deno,
ffmpeg and mpv into `~/.local/termtube-deps/bin/` (on Linux: links your system mpv there); symlinks `~/.local/bin/termtube`; writes `VERSION`
(`dev` for an untagged checkout, which the self-updater never overwrites); optionally creates a desktop entry (Linux) or an app bundle (macOS).
Flags: `--no-deps` (Python environment only), `--no-prompt`, `--refresh` (see [Update](#update)), `--help`.

A full run **deletes and recreates the whole install directory, including its venv**, then reinstalls. That is slow (30 to 60 s of pip) but
clean. To only pick up code changes use `--refresh`.

You can also skip `setup.sh` the first time: running `./termtube` from a fresh clone calls it for you with `--no-prompt`.

### Windows

```powershell
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git $HOME\termtube
cd $HOME\termtube
.\scripts\setup.ps1                # add -NoPrompt for a non-interactive install, -NoDeps to skip the tool downloads
```

`setup.ps1` installs to `%LOCALAPPDATA%\Programs\TermTube\` (code, `.venv`, launcher), keeps an existing `.venv` across reinstalls (it stashes and
restores it, and skips pip when `requirements.txt` is unchanged), downloads Deno, ffmpeg and the headless `mpv.exe` into
`%LOCALAPPDATA%\termtube-deps\bin\`, and adds the app folder to your user PATH. **Open a new terminal afterwards.** Run it under Windows PowerShell
5.1 (the version CI tests) or PowerShell 7; `termtube.cmd` sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, so always start the app through `termtube`.

### If a download fails

The tool downloads use GitHub's release pages and the anonymous API (60 requests an hour per address). On a shared network the API may answer
`403 rate limit exceeded`; setup then reads the latest tag from the release page redirect instead. If it still fails, wait and re-run, or set
`GITHUB_TOKEN` in the environment (it is sent to `api.github.com` only). Failed tool downloads are not fatal to the rest of setup; `termtube --update`
retries them. Behind a corporate TLS proxy, expect certificate errors; the script prints guidance.

## First launch

```bash
termtube --version                 # prints e.g. "TermTube v0.6.0" (or "TermTube dev" when installed from a checkout that is not exactly on a release tag)
termtube                           # starts the UI
termtube --debug                   # same, with a log file and the Ctrl+D log panel
termtube --browser-help            # how the browser-cookie setting works
```

On the first run a notice may say your terminal cannot draw real images; choose "OK" (or "Never show again"). The Home tab needs a signed-in browser
to be personal (Settings `,` → Browser); everything else works without one. Press `?` for help.

## Update

| Want | Command | Touches |
|---|---|---|
| Everything: tools, yt-dlp, app code | `termtube --update` | re-downloads Deno/ffmpeg/mpv, `pip install -U yt-dlp yt-dlp-ejs`, replaces `src/` and `scripts/` from the latest GitHub release (a `dev` install is never overwritten); exits non-zero if any step failed |
| Only the code of this checkout, into the installed app | `bash scripts/setup.sh --refresh` | `src/`, `scripts/`, `assets/`, launcher, `VERSION`. **No network, no venv change.** It warns if `requirements.txt` changed since the venv was built; then run a full setup. |
| Windows, same | re-run `.\scripts\setup.ps1` | keeps the venv; skips pip when unchanged |
| Only yt-dlp, from the UI | happens on demand | the app offers it when feed loading fails with a stale-extractor error |

Nothing updates in the background.

## Uninstall and reinstall on another machine

**Uninstall** (any of these):

```bash
termtube --uninstall                # the launcher runs the uninstall script for your OS and asks first
bash scripts/uninstall.sh           # macOS/Linux: removes the app, venv, launcher link and the managed tools
bash scripts/uninstall.sh --purge   # also removes config, history, playlists, cache and logs
bash scripts/uninstall.sh --force   # no confirmation prompt
.\scripts\uninstall.ps1             # Windows; -Purge, -Force likewise
```

Default uninstall **keeps** your config folder (settings, history, playlists), your cache and your downloaded media (`Documents/TermTube`). `--purge` removes
the first three but never your downloads.

**Move to another machine:**

1. On the old machine, copy the config folder (`~/.config/TermTube/` or `%APPDATA%\TermTube\`): `config.yaml`, `history.json`, `playlists.json`.
   Skip the cache; it rebuilds. Your downloads are plain files in `Documents/TermTube` (copy them if you want them).
2. On the new machine, install following [Install](#install) (Linux: install mpv first).
3. Put the copied files in the new config folder **before** the first launch.
4. Open `config.yaml` and check the two machine-specific settings: `video_dir` / `audio_dir` (paths that must exist or be creatable there) and `browser`
   (the browser that is signed in to YouTube on *that* machine; or `auto`).
5. `termtube --version`, then `termtube`.

To reinstall on the same machine without losing anything: `bash scripts/uninstall.sh` (no `--purge`), then `bash scripts/setup.sh`.

## Develop

```bash
git clone https://github.com/Adam-Yung/TermTube.git && cd TermTube
scripts/dev-setup.sh --install      # creates ./.venv and installs requirements-dev.txt through .venv/bin/python -m pip
scripts/dev-setup.sh --check        # read-only: is .venv really this checkout's own, separate from the installed app's?
.venv/bin/python src/main.py        # run from the checkout (or ./termtube, which prefers the venv next to it)
```

Rules that matter: use `.venv/bin/python -m pip`, never a bare `pip` (a bare `pip` once installed packages into the *installed app's* venv);
use `--config FILE` and `TERMTUBE_CACHE_DIR` when you want a run that does not touch your real data; `scripts/dev-setup.sh --recreate` rebuilds
`.venv` from scratch. On Windows the dev scripts are bash (`verify.sh`, `dev-setup.sh`): use Git Bash or WSL; the venv python is `.venv\Scripts\python.exe`.

Python style, comments, tests, docs and the commit gate are in [AGENTS.md](../../AGENTS.md). Where code lives: [architecture.md](../features/architecture.md);
what each file is for: `docs/code/<path>.md`.

## Test

| What | Command | Time | Needs |
|---|---|---|---|
| **The gate** (run before every commit) | `scripts/verify.sh` | ~45 s | the venv; prints `GATE-OK` only if everything passed |
| Unit / integration / headless UI tests | `.venv/bin/python -m pytest src/tests/unit` (also `integration`, `tui`) | seconds | nothing external |
| The real app in a real terminal | `.venv/bin/python scripts/e2e-local.py` | ~10 s | mpv; silent; no network; isolated config, cache and sockets |
| Real mpv over its control channel | `.venv/bin/python scripts/smoke-ipc.py` | ~3 s | mpv |
| Live YouTube still parses | `.venv/bin/python scripts/canary-live.py` | ~5 s | network |
| Source speeds | `.venv/bin/python scripts/bench-sources.py` | ~1 min | network |

`verify.sh` runs: byte-compile, `ruff check .` (`ruff.toml`), all tests, `check-dead-code.py`, `scripts/gate/run.sh` (skipped with `DESLOP_GATES=0`; needs `shellcheck` and `npm ci --ignore-scripts --prefix scripts/gate/lint`). It uses
`$RUFF`, else `.venv/bin/ruff`, else `ruff` on PATH. Never trust a piped exit code: look for the literal `GATE-OK`.
The tests never touch the network, your browser profile or your real config and cache. The same checks run on GitHub for Linux, macOS and Windows;
what a green run proves: [ci.md](ci.md).

## Environment variables and files

| Name | Effect |
|---|---|
| `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` | honoured on Linux/macOS for the config and cache folders |
| `APPDATA`, `LOCALAPPDATA` | config and app/cache/tool folders on Windows |
| `TERMTUBE_CACHE_DIR` | overrides the cache folder on every platform (used by the end-to-end run) |
| `XDG_RUNTIME_DIR` | where mpv's control sockets go on Unix; else `/tmp/termtube-<uid>/` |
| `GITHUB_TOKEN` | optional, for the installer's release lookups; sent to `api.github.com` only |
| `MPV_HOME` | mpv's own: a config directory; the end-to-end run uses it to silence audio |
| `RUFF` | which ruff `verify.sh` uses |
| `MYYOUTUBE_IMAGES=1` | force pixel thumbnails on inside tmux |

Files: `config.yaml`, `history.json` (slim records, 500 by default, `history_max`), `playlists.json` in the config folder; per-video JSON, feed id lists, thumbnails and SponsorBlock
data in the cache folder; a log per `--debug` run in the temp folder.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Required tools missing from <dir>` | The check accepts only the managed folder. Re-run setup. On Linux the installer links your system mpv into it; install mpv first. |
| `✗ Audio failed … (exit code N)` | `termtube --debug`, play again, read `<temp>/TermTube/<timestamp>-mpv.log` (mpv's own log) and the main log. A missing audio device on a server is a common cause. |
| Audio or the UI freezes only with `--debug` | Fixed 2026-11-16 (a lock deadlock in the log panel); update to the latest code. |
| Home feed empty | Settings → Browser must name a browser that is signed in to YouTube, or `auto`. `browser: none` gives a generic or empty feed by design. |
| An update prompt after a feed error | The error text looked like a stale yt-dlp extractor. Accept the prompt or run `termtube --update`. |
| `UnicodeDecodeError` on Windows | The app was started without `PYTHONUTF8=1`; start it with `termtube` (`termtube.cmd`). |
| No audio on Windows | `%LOCALAPPDATA%\termtube-deps\bin\mpv.exe` is missing (audio never uses mpv.net, which always opens a window). Run `termtube --update`. |
| Weird colours or no thumbnails | Terminal without 24-bit colour or image support. Try another terminal; tmux disables pixel images. |
| Sockets: `Address already in use` / stale mpv | Startup removes stale sockets and kills leftover TermTube mpv processes; if it persists, delete `/tmp/termtube-<uid>/`. |
| Everything is odd after an upgrade | `termtube --clear-cache`. |
| Installed app differs from your checkout | `bash scripts/setup.sh --refresh`. |
| `scripts/verify.sh` says the venv is wrong | `scripts/dev-setup.sh --check`, then `--recreate`. |

Debug workflow: `termtube --debug` writes `<temp>/TermTube/<timestamp>.log` and mirrors it in the `Ctrl+D` panel (`--level WARNING` to quiet it).
mpv start-up timing guide: [startup-debugging.md](startup-debugging.md).

## For agents

Everything an agent needs before changing code:

1. Read [AGENTS.md](../../AGENTS.md) (hard safety rule: no flagged or unverified downloads; model budget; code and doc rules), then
   [../status.md](../status.md), [../features/architecture.md](../features/architecture.md) and the `docs/code/<path>.md` mirror of any file you touch.
2. Network: anonymous requests to `youtube.com` (and its image CDN) are allowed for measuring and recording fixtures; nothing else without asking. Never read
   browser profiles or cookie files. Installing packages or tools is a download: ask, name the package and version.
3. Work loop: edit, `scripts/verify.sh` until `GATE-OK`, update the mirror, `status.md` and the decision log in the same commit, commit.
   Do not push, merge or force anything unless asked.

Recipes:

```bash
# Is the environment sane?
scripts/dev-setup.sh --check

# Run the whole gate and read the verdict (never judge by a piped exit code)
bash scripts/verify.sh > /tmp/gate.out 2>&1; tail -3 /tmp/gate.out; grep -c '^GATE-OK' /tmp/gate.out

# Drive the real TUI by hand in a pseudo-terminal, isolated from real data (tmux)
mkdir -p /tmp/t && printf 'browser: none\nthumbnail_warning_dismissed: true\n' > /tmp/t/config.yaml
tmux new-session -d -s t -x 150 -y 46 ".venv/bin/python src/main.py --config /tmp/t/config.yaml"
tmux send-keys -t t / ; tmux capture-pane -t t -p     # keys and screen; do not redirect the app's stderr: Textual draws on it

# Break the app on purpose to check a test or pipeline step really fails (then restore with git checkout)
# CI: watch and read runs without opening a browser
gh run list --limit 5;  gh run view <id> --log-failed;  gh workflow run test.yml -f repeat=10   # stability: 10 end-to-end runs per platform
```

Headless UI tests: `app.run_test(size=..., notifications=True)` (notifications are off by default, so toasts only exist with the flag). Test
fixture video ids must be 11 characters or the app treats the feed as empty. A background worker must tolerate its app or screen being gone (see the
`NoMatches` / `NoActiveAppError` handling in `detail_focus.py`).

Pitfalls found the hard way: keep `COLUMNS`/`LINES` out of child environments for pty runs; read and write text files with `encoding="utf-8"` (a test
enforces it); `textual.markup.escape` leaves a lone `[` alone, use `tui/fmt.escape_markup`; never block inside a logging sink.
