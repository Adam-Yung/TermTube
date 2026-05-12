# TermTube

A lightning-fast YouTube client for your terminal. Browse your home feed, search, listen to audio in the background, and watch videos — all without leaving the command line.

## Why TermTube?

- **Instant startup** — cached feeds load in milliseconds; no browser overhead
- **Lightweight** — pure Python TUI with minimal resource usage
- **Background audio** — listen to YouTube while you work, with seek/pause/queue controls
- **Native terminal graphics** — high-resolution thumbnails via Kitty/Sixel protocols, with universal chafa fallback
- **Keyboard-driven** — vim-style navigation, page-based browsing, zero mouse required
- **Privacy-respecting** — runs locally, no telemetry, no accounts beyond your existing YouTube cookies
- **Cross-platform** — works on macOS, Linux, and Windows

## Installation

### Prerequisites

| Tool | Purpose | macOS | Linux (apt) | Windows |
|------|---------|-------|-------------|---------|
| Python 3.11+ | Runtime | `brew install python@3.12` | `sudo apt install python3.12` | `winget install Python.Python.3.12` |
| yt-dlp | YouTube data | `brew install yt-dlp` | `sudo apt install yt-dlp` | `winget install yt-dlp.yt-dlp` |
| mpv | Playback | `brew install mpv` | `sudo apt install mpv` | `winget install mpv.net` |
| chafa | Thumbnails (optional) | `brew install chafa` | `sudo apt install chafa` | `winget install hpjansson.Chafa` |
| ffmpeg | Audio conversion (optional) | `brew install ffmpeg` | `sudo apt install ffmpeg` | `winget install Gyan.FFmpeg` |

### Quick Install — macOS / Linux

```bash
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/termtube
cd ~/termtube
bash setup.sh
```

The installer will:
1. Detect your package manager (brew, apt, dnf, pacman, zypper, apk)
2. Offer to install missing dependencies automatically
3. Ask whether you want standard or developer mode
4. Create a Python virtual environment
5. Add `termtube` to your PATH

#### Options

```bash
bash setup.sh              # Interactive install (recommended)
bash setup.sh --sync       # Developer mode (symlink, edits are live)
bash setup.sh --deps       # Auto-install dependencies without prompting
bash setup.sh --no-prompt  # Non-interactive (accept all defaults)
```

### Quick Install — Windows

```powershell
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git $HOME\termtube
cd $HOME\termtube
.\setup.ps1
```

The installer will:
1. Offer to install missing dependencies via winget
2. Create a Python virtual environment
3. Add `termtube` command to your user PATH

> **Recommended:** Use [Windows Terminal](https://aka.ms/terminal) for full Sixel graphics and thumbnail support.

#### Options

```powershell
.\setup.ps1              # Interactive install (recommended)
.\setup.ps1 -Sync        # Developer mode (NTFS junction)
.\setup.ps1 -Deps        # Auto-install dependencies via winget
.\setup.ps1 -NoPrompt    # Non-interactive
```

### Development Mode

For development (edits take effect immediately without re-running setup):

```bash
# macOS / Linux
bash setup.sh --sync

# Windows
.\setup.ps1 -Sync
```

### Uninstalling

```bash
# macOS / Linux
bash uninstall.sh            # Preserve config
bash uninstall.sh --purge    # Remove everything

# Windows
.\uninstall.ps1              # Preserve config
.\uninstall.ps1 -Purge      # Remove everything

# Or from anywhere:
termtube --uninstall
```

## Quick Start

1. **Launch**: Run `termtube` in your terminal
2. **Set up cookies** (required for Home Feed & Subscriptions):

```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ~/.config/TermTube/cookies.txt \
       --skip-download --quiet --no-warnings \
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Replace `chrome` with `firefox`, `brave`, or `edge` as needed.

On Windows, the config path is `%APPDATA%\TermTube\cookies.txt`.

3. **Browse**: Use `j`/`k` to navigate, `]`/`[` to switch pages, `Enter` for actions

## Navigation

### Browsing

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up in list |
| `]` / `[` | Next page / previous page |
| `g` / `G` | First page / last page |
| `Enter` | Open actions menu |
| `/` | Search YouTube |
| `r` | Refresh current feed |
| `` ` `` | Quick-nav page picker |
| `F1`–`F6` | Jump to tab (Home, Subs, Search, History, Library, Playlists) |

### Playback

| Key | Action |
|-----|--------|
| `w` | Watch video (opens mpv) |
| `W` | Watch with quality picker |
| `l` | Listen (audio) / seek +5s |
| `L` | Listen quality / seek +10s |
| `h` / `H` | Seek -5s / -10s |
| `Space` | Pause / resume audio |
| `s` | Stop audio / open channel |
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
| `?` | Help |
| `q` | Quit |

## Configuration

Config location:
- **macOS / Linux:** `~/.config/TermTube/config.yaml`
- **Windows:** `%APPDATA%\TermTube\config.yaml`

Created on first run with these defaults:

```yaml
browser: chrome          # Browser for cookies (chrome/firefox/brave/edge)
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

## Cookie Setup

TermTube needs YouTube session cookies for personalized feeds.

**Option A — Export via yt-dlp (recommended):**

```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ~/.config/TermTube/cookies.txt \
       --skip-download --quiet --no-warnings \
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Option B — Browser extension:**

1. Install "Get cookies.txt LOCALLY" (Chrome) or "cookies.txt" (Firefox)
2. Visit youtube.com, export as Netscape format
3. Save to `~/.config/TermTube/cookies.txt` (or `%APPDATA%\TermTube\cookies.txt` on Windows)

**Option C — Direct browser access:**

Set `cookies_file: null` in config. TermTube reads cookies directly from your browser session.

## Platform Notes

### macOS

Works out of the box. Homebrew is the recommended package manager.

### Linux

Tested on Ubuntu, Fedora, and Arch. The setup script detects apt, dnf, pacman, zypper, and apk automatically.

For best thumbnail quality, use a terminal that supports Sixel or the Kitty graphics protocol (kitty, iTerm2, WezTerm, foot).

### Windows

- **Windows Terminal** (recommended): Full Sixel graphics support for high-quality thumbnails
- **PowerShell 7**: TUI works, thumbnails via chafa symbols
- **Legacy cmd.exe**: Basic support, chafa symbols for thumbnails

mpv on Windows uses named pipes for IPC communication (instead of Unix sockets). This is handled automatically.

## Testing

TermTube has a comprehensive test suite with 200+ tests covering unit logic, integration with external tools, and TUI interactions.

### Running Tests Locally

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run by layer
pytest tests/unit/           # Pure logic tests (fast, no I/O)
pytest tests/integration/    # Subprocess/IPC mocking tests
pytest tests/tui/            # Textual headless TUI tests

# Run a specific test file
pytest tests/unit/test_cache.py -v

# Run with verbose output
pytest -v --tb=short
```

### Visual Snapshot Tests (optional)

```bash
pip install pytest-textual-snapshot
pytest tests/snapshots/

# Accept new baselines after intentional UI changes
pytest tests/snapshots/ --snapshot-update
```

### CI / GitHub Actions

Tests run automatically on every push and pull request via `.github/workflows/test.yml`. The pipeline has three jobs:
- **unit-and-integration** — runs `tests/unit/` and `tests/integration/`
- **tui-tests** — runs `tests/tui/` with async support
- **snapshot-tests** — runs `tests/snapshots/` and uploads diff report on failure

No external tools (yt-dlp, mpv) are needed in CI — all external dependencies are mocked.

## Debugging

```bash
termtube --debug                   # full logging
termtube --debug --level WARNING   # only warnings+
```

Log location:
- **macOS / Linux:** `$TMPDIR/TermTube/<timestamp>.log`
- **Windows:** `%TEMP%\TermTube\<timestamp>.log`

Toggle the in-app debug panel with `Ctrl+D`.
