<div align="center">

<img src="assets/termtube.png" alt="TermTube" width="600">

# TermTube

**A lightning-fast YouTube client for your terminal.**

Browse your home feed, search, listen in the background, and watch videos — all without leaving the command line.

[![Tests](https://github.com/Adam-Yung/TermTube/actions/workflows/test.yml/badge.svg)](https://github.com/Adam-Yung/TermTube/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](#platform-notes)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

---

## Why TermTube?

| | |
|---|---|
| **Instant startup** | Cached feeds load in milliseconds — no browser overhead |
| **Background audio** | Listen to YouTube while you work, with seek/pause/queue controls |
| **Native thumbnails** | High-res images via Kitty/Sixel protocols, with universal chafa fallback |
| **Keyboard-driven** | Vim-style navigation, page-based browsing, zero mouse required |
| **Privacy-respecting** | Runs locally, no telemetry, no accounts beyond your existing YouTube cookies |
| **Cross-platform** | macOS, Linux, and Windows — one codebase |
| **Self-updating** | Binary tools stay current automatically; no cron job needed |

---

## Installation

### Prerequisites

| Tool | Purpose | macOS | Linux | Windows |
|------|---------|-------|-------|---------|
| Python 3.11+ | Runtime | `brew install python@3.12` | `sudo apt install python3.12` | `winget install Python.Python.3.12` |
| yt-dlp (nightly) | YouTube data | auto-installed | auto-installed | auto-installed |
| Deno | JS challenge solver | auto-installed | auto-installed | auto-installed |
| mpv | Video/audio playback | `brew install mpv` | `sudo apt install mpv` | bundled by setup |
| chafa | Thumbnails (optional) | `brew install chafa` | `sudo apt install chafa` | `winget install hpjansson.Chafa` |
| ffmpeg | Audio conversion (optional) | `brew install ffmpeg` | `sudo apt install ffmpeg` | `winget install Gyan.FFmpeg` |

> **Note:** TermTube uses **yt-dlp nightly** rather than the stable release, because YouTube's extractor changes daily. The setup script downloads it automatically.  
> **Deno** is required by yt-dlp (since November 2025) to solve YouTube's JavaScript challenges. The setup script handles this too.

---

### macOS / Linux

```bash
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/termtube
cd ~/termtube
bash setup.sh
```

The installer will:
1. Detect your package manager (brew, apt, dnf, pacman, zypper, apk)
2. Download **yt-dlp nightly** directly from GitHub
3. Install **Deno** via the official installer
4. Offer to install remaining dependencies via your package manager
5. Create a Python virtual environment and install packages
6. Add `termtube` to your PATH

**Options:**
```bash
bash setup.sh              # Interactive install (recommended)
bash setup.sh --sync       # Developer mode (symlink, edits are live)
bash setup.sh --deps       # Auto-install all dependencies without prompting
bash setup.sh --no-prompt  # Non-interactive (accept all defaults)
```

---

### Windows

```powershell
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git $HOME\termtube
cd $HOME\termtube
.\setup.ps1
```

The installer will:
1. Download yt-dlp nightly and Deno from GitHub automatically
2. Bundle a standalone headless `mpv.exe` for audio playback
3. Create a Python virtual environment and install packages
4. Add `termtube` to your user PATH

> **Recommended:** Use [Windows Terminal](https://aka.ms/terminal) for full Sixel graphics and best thumbnail quality.

**Options:**
```powershell
.\setup.ps1              # Interactive install (recommended)
.\setup.ps1 -Sync        # Developer mode (NTFS junction)
.\setup.ps1 -Deps        # Auto-install via winget
.\setup.ps1 -NoPrompt    # Non-interactive
```

---

### Developer Mode

For active development — edits take effect immediately without re-running setup:

```bash
# macOS / Linux
bash setup.sh --sync

# Windows
.\setup.ps1 -Sync
```

---

### Uninstalling

```bash
# macOS / Linux
bash uninstall.sh            # Preserve config and data
bash uninstall.sh --purge    # Remove everything

# Windows
.\uninstall.ps1
.\uninstall.ps1 -Purge

# Or from anywhere:
termtube --uninstall
```

---

## Quick Start

**1. Launch:**
```bash
termtube
```

**2. Set up cookies** (required for Home Feed & Subscriptions):
```bash
# macOS / Linux
yt-dlp --cookies-from-browser chrome \
       --cookies ~/.config/TermTube/cookies.txt \
       --skip-download --quiet --no-warnings \
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Windows
yt-dlp --cookies-from-browser chrome `
       --cookies "$env:APPDATA\TermTube\cookies.txt" `
       --skip-download --quiet --no-warnings `
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```
Replace `chrome` with `firefox`, `brave`, or `edge` as needed.

**3. Browse:** Use `j`/`k` to navigate, `]`/`[` to switch pages, `Enter` for the actions menu.

---

## Keyboard Reference

### Navigation

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `]` / `[` | Next page / previous page |
| `g` / `G` | First / last page |
| `Enter` | Open actions menu |
| `/` | Search YouTube |
| `r` | Refresh current feed |
| `` ` `` | Quick-nav page picker |
| `F1`–`F6` | Jump to tab (Home, Subs, Search, History, Library, Playlists) |

### Playback

| Key | Action |
|-----|--------|
| `w` | Watch video (opens mpv fullscreen) |
| `W` | Watch with quality picker |
| `l` | Listen (background audio) |
| `L` | Listen with quality picker |
| `h` / `H` | Seek −5s / −10s |
| `l` / `L` | Seek +5s / +10s (when audio playing) |
| `Space` | Pause / resume audio |
| `s` | Stop audio |
| `0`–`9` | Seek to 0%–90% |
| `e` | Add to audio queue |
| `>` | Skip to next in queue |

### Actions

| Key | Action |
|-----|--------|
| `d` | Download video |
| `a` | Download audio |
| `y` | Copy video URL |
| `p` | Add to playlist |
| `b` | Open in browser |
| `,` | Settings |
| `?` | Help overlay |
| `q` | Quit |

---

## Configuration

Config location:
- **macOS / Linux:** `~/.config/TermTube/config.yaml`
- **Windows:** `%APPDATA%\TermTube\config.yaml`

Created automatically on first run:

```yaml
browser: chrome          # Browser for cookies: chrome | firefox | brave | edge
cookies_file: ~/.config/TermTube/cookies.txt
video_dir: ~/Documents/TermTube/Video
audio_dir: ~/Documents/TermTube/Audio
preferred_quality: best  # best | 1080 | 720 | 480
preferred_player: mpv
theme: crimson           # crimson | amber | ocean | midnight
thumbnail_format: auto   # auto | symbols | ascii
cache_ttl:
  home: 3600
  subscriptions: 3600
  search: 1800
  metadata: 86400
```

---

## Cookie Setup

TermTube needs YouTube session cookies for personalized feeds (Home, Subscriptions).

**Option A — Export via yt-dlp (recommended):**
```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ~/.config/TermTube/cookies.txt \
       --skip-download --quiet --no-warnings \
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Option B — Browser extension:**
1. Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome) or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox)
2. Visit youtube.com, export as Netscape format
3. Save to `~/.config/TermTube/cookies.txt` (or `%APPDATA%\TermTube\cookies.txt` on Windows)

**Option C — Direct browser access:**
Set `cookies_file: null` in your config. TermTube reads cookies directly from your browser session.

---

## Automatic Updates

On each clean exit, TermTube silently checks if tools need updating (once per week):

| Tool | Update method |
|------|---------------|
| yt-dlp | `yt-dlp --update-to nightly` |
| Deno | `deno upgrade` / `brew upgrade` / winget |
| mpv | `brew upgrade mpv` / winget |
| ffmpeg | `brew upgrade ffmpeg` / winget |
| chafa | `brew upgrade chafa` / winget |

A brief notification appears on next launch: `yt-dlp updated 2026.03.17 → 2026.05.05`.

To update immediately:
```bash
termtube --update
```

---

## Platform Notes

### macOS
Works out of the box. Homebrew is the recommended package manager.

### Linux
Tested on Ubuntu, Fedora, and Arch. The setup script auto-detects apt, dnf, pacman, zypper, and apk.

For best thumbnail quality, use a terminal that supports Sixel or the Kitty graphics protocol (kitty, WezTerm, foot, iTerm2).

### Windows
- **Windows Terminal** (recommended) — full Sixel graphics for high-quality thumbnails
- **PowerShell 7** — full TUI support, chafa symbol thumbnails
- **Legacy cmd.exe** — basic support

mpv on Windows uses named pipes for IPC (instead of Unix sockets) — handled automatically.

---

## Testing

TermTube has 200+ tests covering unit logic, integration with external tools, and full TUI interactions.

```bash
# Run all tests (requires venv activated or use the venv Python directly)
pytest

# By layer
pytest tests/unit/           # Pure logic — fast, no I/O
pytest tests/integration/    # Subprocess/IPC tests
pytest tests/tui/            # Headless Textual TUI tests

# Verbose
pytest -v --tb=short
```

**Visual snapshot tests** (optional):
```bash
pip install pytest-textual-snapshot
pytest tests/snapshots/
pytest tests/snapshots/ --snapshot-update   # Accept new baselines after UI changes
```

CI runs automatically on every push and pull request via GitHub Actions.

---

## Debugging

```bash
termtube --debug                   # Full debug logging
termtube --debug --level WARNING   # Warnings and above only
```

Toggle the in-app debug panel with `Ctrl+D`.

Log location:
- **macOS / Linux:** `$TMPDIR/TermTube/<timestamp>.log`
- **Windows:** `%TEMP%\TermTube\<timestamp>.log`
