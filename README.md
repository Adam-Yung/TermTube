# TermTube

A lightning-fast YouTube client for your terminal. Browse your home feed, search, listen to audio in the background, and watch videos — all without leaving the command line.

## Why TermTube?

- **Instant startup** — cached feeds load in milliseconds; no browser overhead
- **Lightweight** — pure Python TUI with minimal resource usage
- **Background audio** — listen to YouTube while you work, with seek/pause/queue controls
- **Native terminal graphics** — high-resolution thumbnails via Kitty/Sixel protocols, with universal chafa fallback
- **Keyboard-driven** — vim-style navigation, page-based browsing, zero mouse required
- **Privacy-respecting** — runs locally, no telemetry, no accounts beyond your existing YouTube cookies

## Installation

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.11+ | Runtime | `brew install python@3.11` / `apt install python3.11` |
| yt-dlp | YouTube data extraction | `brew install yt-dlp` / `pip install yt-dlp` |
| mpv | Media playback | `brew install mpv` / `apt install mpv` |
| chafa | Terminal thumbnails (optional) | `brew install chafa` / `apt install chafa` |
| ffmpeg | Audio conversion (optional) | `brew install ffmpeg` / `apt install ffmpeg` |

### Quick Install

```bash
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/termtube
cd ~/termtube
bash setup.sh
```

The installer creates a virtual environment, installs Python dependencies, and adds `termtube` to your PATH.

### Development Mode

For development (edits take effect immediately):

```bash
bash setup.sh --sync
```

### Uninstalling

```bash
bash uninstall.sh
```

This removes the installation directory, virtual environment, CLI symlink, and config files.

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

Config lives at `~/.config/TermTube/config.yaml` (created on first run):

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
3. Save to `~/.config/TermTube/cookies.txt`

**Option C — Direct browser access:**

Set `cookies_file: null` in config. TermTube reads cookies directly from your browser session.

## Debugging

```bash
termtube --debug                   # full logging
termtube --debug --level WARNING   # only warnings+
```

Logs go to `$TMPDIR/TermTube/<timestamp>.log`. Toggle the in-app debug panel with `Ctrl+D`.
