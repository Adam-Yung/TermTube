<div align="center">

<img src="assets/termtube.png" alt="TermTube" width="600">

# TermTube

**A YouTube client for your terminal.**

Browse, search, listen in the background and watch, without leaving the command line.

[![Pipeline](https://github.com/Adam-Yung/TermTube/actions/workflows/test.yml/badge.svg)](https://github.com/Adam-Yung/TermTube/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](#platform-notes)

</div>

---

## What it does

- **Home feed, subscriptions, search, channels, history and a Library** in tabs, driven entirely from the keyboard (vim-style `hjkl`).
- **List tools** on every list: `f` filters all loaded pages as you type, `m`/`M` mark rows, `D` removes them after one `y`/N, `u` undoes (History and playlists; Library deletes files for good).
- **History** with day headers, resume points (`▶ 2:05 / 10:00`), watch time and sorting; `Y` switches between local history, your YouTube history and Watch Later. `history: false` records nothing.
- **Library** with a left rail (All downloads, Videos, Audio and your local playlists), search tokens (`type:audio`, `dur:<10m`) and delete of the files with sizes shown first.
- **Background audio** through a headless mpv: queue (`q` shows, reorders and clears it), pause, seek, SponsorBlock auto-skip. It keeps playing while you browse.
- **Video** in an mpv window, with progress and controls in the terminal.
- **Downloads** (video as mp4, audio as mp3) with progress, then a **Library** tab that lists and plays what you downloaded.
- **Thumbnails** as real images (Kitty, Sixel) where the terminal supports it, as colour half-block art everywhere else.
- **Fast and light:** cached feeds open instantly; metadata comes from YouTube's own web API (InnerTube) in 0.2 to 0.5 s, with yt-dlp as the fallback.
- **Private by default:** no telemetry, no account login inside the app. Your browser's YouTube cookies are read only for the two things that need an account (Home feed, subscription list), only when first needed, and never leave the process. See [accounts and cookies](docs/features/accounts-and-cookies.md).
- **Four colour themes** (crimson, amber, ocean, midnight).

It runs on **macOS, Linux and Windows**. A GitHub pipeline installs it from scratch on all three, drives the installed app in a real terminal with real mpv, and must pass before a change counts as working ([what that proves](docs/guides/ci.md)).

---

## Install

### You need

| Tool | Why | Get it |
|---|---|---|
| Python 3.11 or newer | runs the app | [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12` |
| git | to clone the repo | usually installed; [git-scm.com](https://git-scm.com) |
| **mpv** (Linux only) | audio and video playback | `sudo apt install mpv` · `sudo dnf install mpv` · `sudo pacman -S mpv` |

The setup script installs everything else: **Deno, ffmpeg and mpv** (macOS, Windows) are downloaded from GitHub releases into a TermTube-managed
folder, and **yt-dlp** is installed as a Python package. Linux has no static mpv build, so install mpv first; the script then links it into the
managed folder, which is where TermTube looks for it. Setup needs internet access to `github.com` and PyPI.

### macOS and Linux

```bash
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/termtube
cd ~/termtube
bash scripts/setup.sh
```

Then open a new terminal and run `termtube`. Options: `--no-prompt` (accept all defaults, for scripts), `--no-deps` (Python environment only),
`--refresh` (replace only the installed code from this checkout: no network, venv untouched).

### Windows

```powershell
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git $HOME\termtube
cd $HOME\termtube
.\scripts\setup.ps1
```

Then **open a new terminal** (setup adds `%LOCALAPPDATA%\Programs\TermTube` to your user PATH) and run `termtube`. Options: `-NoPrompt`, `-NoDeps`.
Use [Windows Terminal](https://aka.ms/terminal) for the best result.

### Where things go

| | macOS / Linux | Windows |
|---|---|---|
| App code and its Python environment | `~/.local/share/TermTube/` | `%LOCALAPPDATA%\Programs\TermTube\` |
| Deno, ffmpeg, mpv | `~/.local/termtube-deps/bin/` | `%LOCALAPPDATA%\termtube-deps\bin\` |
| `termtube` command | `~/.local/bin/termtube` (symlink) | `termtube.cmd` in the app folder, on your PATH |
| Config, history, playlists | `~/.config/TermTube/` | `%APPDATA%\TermTube\` |
| Cache | `~/.cache/termtube/` | `%LOCALAPPDATA%\TermTube\cache\` |
| Debug logs (`--debug` only) | `$TMPDIR/TermTube/` | `%TEMP%\TermTube\` |
| Downloads | `~/Documents/TermTube/Video` and `/Audio` | same under `Documents` |

The full install, update and troubleshooting guide, including how to move to another machine, is [docs/guides/setup.md](docs/guides/setup.md).

---

## Using it

Run `termtube`. The tabs are **Home**, **Subscriptions**, **Search**, **History**, **Library**, **Help**. Playlists live in the Library rail.

- Move with `j`/`k`, change page with `h`/`l`, jump to the first or last item with `g`/`G`, change tab with `H`/`L` or `F1`..`F6`.
- `Enter` opens the action menu for the highlighted video; every action also has its own key, shown in the footer and the in-app help (`?`).
- `/` searches. `a` plays the audio in the background, `v` watches the video, `d` downloads, `c` opens the channel, `p` adds to a playlist.
- `f` filters the list, `m`/`M` mark rows, `D` removes (then `u` undoes), `q` opens the audio queue, `,` opens settings.
- `Ctrl+Q` quits (stops audio; the queue is not saved).

### Keys

| Move | | Play | |
|---|---|---|---|
| `j` `k` | cursor down / up | `a` `A` | audio / choose quality first |
| `h` `l` (or arrows) | previous / next page | `v` `V` | watch video / choose quality first |
| `g` `G` | first / last item | `e` | add audio to the queue |
| `H` `L` | previous / next tab | `>` `<` | next queued track / previous track |
| `Enter` | action menu | `Space` | pause / resume audio |
| `Esc` `Backspace` | back | `x` | stop audio and clear the queue |
| `F1`..`F6`, `` ` `` | jump to a tab / tab picker | `[` `]` `{` `}` | seek ∓5 s / ∓10 s |
| | | `0`..`9` | seek to 0 % to 90 % |

| Row actions | | App | |
|---|---|---|---|
| `d` | download (video or audio) | `/` | search |
| `c` | channel page (`s` sort, `r` reload) | `r` | refresh the feed |
| `p` | add to a local playlist | `,` | settings |
| `f` `m` `M` | filter / mark row / mark page | `D` `u` | remove marked or current / undo |
| `Y` | History: cycle source | `q` | audio queue |
| `y` | copy the URL | `?` | help |
| `b` | open in the browser | `Ctrl+Q` | quit |

On a playlist or Mix row, `v` `a` `e` play it as video, as audio, or queue it without opening it; in a video run `>` `<` step and `q` ends it.

While audio plays, `v` is refused (video and audio would overlap): stop audio with `x` first. A key that cannot act says why in a short notice.
The rules behind the keymap, and every key per screen, are in [docs/features/keybindings.md](docs/features/keybindings.md).

---

## Configuration

`config.yaml` lives in the config folder above and is created on first run. Settings changed in the app (`,`) are saved immediately. Every key is
optional:

```yaml
cookie_prewarm: true     # read the browser's cookies in the background after the first paint (false: only when needed)
browser: auto            # cookie source for Home and Subscriptions: auto | none | firefox | chrome | brave | edge | ...
video_dir: ~/Documents/TermTube/Video
audio_dir: ~/Documents/TermTube/Audio
video_format: "%(title)s_%(uploader)s.%(ext)s"   # yt-dlp output template
audio_format: "%(title)s_%(uploader)s.%(ext)s"
preferred_quality: best  # best | 1080 | 720 | 480 | 360   (default for video downloads)
theme: crimson           # crimson | amber | ocean | midnight
history: true            # false: record nothing in local history (the History tab says so)
history_max: 500         # local history length
resume_playback: true    # remember where you stopped
thumbnail_format: auto   # auto (real images where supported) | symbols (always half-block art)
sponsorblock:
  enabled: true
  auto_skip: true
  categories: [sponsor, selfpromo]
cache_ttl:               # seconds
  home: 3600
  subscriptions: 3600
  search: 1800
  metadata: 86400
```

`termtube --config FILE` uses another file. All keys, validation and defaults: [docs/features/configuration.md](docs/features/configuration.md).

---

## Accounts and cookies

Search, channels, playlists, playback and downloads work **without any account**. Only two things are personal: the **Home feed** and your
**subscription list**. For those, TermTube reads your YouTube cookies from a browser you are already signed in to (`browser: auto` picks one;
Firefox first on macOS because it needs no keychain prompt). The cookies are read the first time one of those two is needed (not at startup),
kept only in memory, limited to `youtube.com` and `google.com`, and never sent to the web API, to stream resolution or to downloads.
`browser: none` turns it all off. `termtube --browser-help` prints the short version; the details are in
[docs/features/accounts-and-cookies.md](docs/features/accounts-and-cookies.md).

---

## Updating, uninstalling, moving to another machine

```bash
termtube --update                  # re-download the tools, upgrade yt-dlp, update the app code, then exit
bash scripts/setup.sh --refresh    # macOS/Linux: copy this checkout's code into the installed app (no downloads)
termtube --uninstall               # the launcher runs scripts/uninstall.sh (uninstall.ps1 on Windows)
bash scripts/uninstall.sh --purge  # also remove config, history, playlists, cache and logs
```

Nothing updates in the background. On another machine, install fresh (above) and copy your config folder across if you want your settings,
history and playlists; the steps and the two things to check (download folders, browser) are in [docs/guides/setup.md](docs/guides/setup.md).

---

## Platform notes

- **macOS:** works out of the box; no Homebrew needed. The first cookie read from Chrome or Brave asks for keychain access; Firefox does not.
- **Linux:** install mpv from your package manager first. Thumbnails as real images need a terminal with Kitty or Sixel graphics (kitty, WezTerm,
  foot, iTerm2 on macOS); other terminals get colour half-block art, which needs 24-bit colour.
- **Windows:** audio uses a bundled headless `mpv.exe` and named pipes (handled for you). mpv.net is not used for background audio because it always
  opens a window. Windows Terminal recommended.
- **tmux:** image protocols are off inside tmux (they flicker); you get half-block thumbnails.

What is tested where: the unit and UI tests run on all three systems on every change, and so does a **real-app run** (installer, launcher, real mpv
over its control channel, the installed app driven by real key presses in a real terminal). What no automated run can see is how the UI looks in
your terminal and how YouTube answers today; a weekly canary checks the latter. See [docs/guides/ci.md](docs/guides/ci.md).

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Required tools missing` at startup | Deno, ffmpeg or mpv is not in the managed folder. Run `bash scripts/setup.sh` (`setup.ps1`) again; on Linux install mpv first. |
| `mpv not found` / audio never starts | Same as above. `termtube --debug` then `Ctrl+D` shows the exact mpv command; its own log is written beside the debug log. |
| Home feed empty or generic | No browser session was found. Open Settings (`,`), pick the browser you are signed in to, or run `termtube --browser-help`. |
| A keychain prompt on macOS | Chrome and Brave protect their cookies with the keychain; choose Firefox, or `browser: none`. |
| Setup says `HTTP Error 403: rate limit exceeded` | GitHub's anonymous API limit on a shared network. Setup falls back to the release page; if it still fails, wait or set `GITHUB_TOKEN` and re-run. |
| Thumbnails are blocks, not images | Your terminal has no Kitty or Sixel support, or you are in tmux. Expected; see Platform notes. |
| `termtube: command not found` | Open a new terminal (PATH changes need it); on macOS/Linux make sure `~/.local/bin` is on your PATH. |
| Anything else | `termtube --debug`, then read `$TMPDIR/TermTube/<timestamp>.log`; `termtube --clear-cache` resets cached data. |

More in [docs/guides/setup.md](docs/guides/setup.md#troubleshooting) and [docs/guides/startup-debugging.md](docs/guides/startup-debugging.md).

---

## Development

```bash
git clone https://github.com/Adam-Yung/TermTube.git && cd TermTube
scripts/dev-setup.sh --install     # a private .venv for this checkout (never a bare pip)
scripts/verify.sh                  # the gate: lint, tests, doc checks. Prints GATE-OK when everything passed
.venv/bin/python scripts/e2e-local.py   # the real app in a pseudo-terminal, silent, no network
```

Read [AGENTS.md](AGENTS.md) first (the rules for code, comments, docs and tests, and the hard safety rule about downloads), then
[docs/README.md](docs/README.md) (the map of the docs), [docs/features/architecture.md](docs/features/architecture.md) (how it is wired) and
[docs/guides/setup.md](docs/guides/setup.md) (everything about running and testing it).

### Layout

```
src/                  the app
  main.py               entry point and CLI
  tui/                  Textual screens, widgets, mixins, audio controller, theme
  innertube.py          YouTube web API client (search, channels, playlists, details)
  ytdlp.py streams.py downloads.py cookies.py    yt-dlp: feeds, stream URLs, downloads, browser cookies
  player.py plat.py bootstrap.py                 mpv control, per-OS paths and processes, tool installer
  cache.py history.py library.py playlist.py store.py config.py    local state
  tests/                unit, integration and headless TUI tests
scripts/              installers, the gate, end-to-end and smoke checks, benchmarks, canary
docs/                 features, guides, decisions, plans, history, and a mirror of every source file (docs/code/)
.github/workflows/    the pipeline (three platforms) and the weekly canary
```
