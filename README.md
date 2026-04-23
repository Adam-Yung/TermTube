# MyYouTube

A modern, beautiful YouTube TUI built on `fzf`, `gum`, `chafa`, `mpv`, and `yt-dlp`. Browse your YouTube home feed, subscriptions, search, and local library — all from your terminal.

## Features

- **Home Page** — Your YouTube recommendations (via browser session cookies)
- **Search** — Full YouTube search with instant results
- **Subscriptions** — Videos from your subscribed channels, by date or channel
- **Library** — Locally saved videos and audio
- **History** — Previously watched videos (local + YouTube history)
- **Video Detail** — Full description, channel info, and actions
- **Thumbnails** — Rendered in-terminal via `chafa` (quality scales with terminal)
- **Watch/Listen** — Stream video via `mpv`/`vlc`, or audio directly in terminal
- **Save** — Download video or audio locally with metadata sidecars
- **Subscribe** — Subscribe to channels from the TUI
- **Open in Browser** — Jump to YouTube in your browser

## Navigation

| Key | Action |
|-----|--------|
| `↑↓` / `jk` | Move up/down in list |
| `←→` / `hl` | Seek ±5s in player |
| `H` `L` | Seek ±10s in player |
| `Ctrl+←→` | Seek ±10s in player |
| `0`–`9` | Seek to 0%–90% of media |
| `Enter` | Select / confirm |
| `Backspace` / `Esc` | Go back |
| `/` | Search (in fzf) |
| `q` | Quit |

## Dependencies

| Tool | Purpose | Install |
|------|---------|---------|
| `yt-dlp` | YouTube engine | `brew install yt-dlp` |
| `fzf` | Interactive list UI | `brew install fzf` |
| `gum` | Beautiful prompts & spinners | `brew install gum` |
| `mpv` | Video/audio playback | `brew install mpv` |
| `chafa` | Terminal thumbnails | `brew install chafa` |
| `jq` | JSON processing | `brew install jq` |
| `ffmpeg` | Media conversion | `brew install ffmpeg` |
| Python 3.10+ | Orchestration | `brew install python3` |

> MyYouTube will prompt you to install any missing dependencies on first run.

## Installation

```bash
git clone https://github.com/yourname/myyoutube
cd myyoutube
pip install -r requirements.txt
chmod +x myt
./myt
# or add to PATH: ln -s $(pwd)/myt /usr/local/bin/myt
```

## Configuration

On first run, `MyYouTube.yaml` is created in the project directory (or `~/.config/myyoutube/config.yaml`). Key settings:

```yaml
browser: chrome            # Browser for YouTube session cookies
                           # Options: chrome, firefox, brave, edge
                           # Note: Safari not supported on macOS (sandboxed)

video_dir: ~/Documents/MyYouTube/Video
audio_dir: ~/Documents/MyYouTube/Audio
video_format: "%(title)s_%(uploader)s.%(ext)s"
audio_format: "%(title)s_%(uploader)s.%(ext)s"

preferred_quality: best    # or: 720, 1080, 4k
preferred_player: mpv      # or: vlc

cache_ttl:
  home: 3600               # 1 hour
  subscriptions: 3600
  search: 1800             # 30 min
  metadata: 86400          # 24 hours
```

## Cookie Setup (Required for Home Feed & Subscriptions)

MyYouTube needs your YouTube session cookies to fetch your home feed, subscriptions, and history. There are two methods — a cookies.txt file is **preferred** as it's faster and more reliable.

### Method 1: cookies.txt (Recommended)

Export your browser cookies to a Netscape-format file:

**Option A — Browser extension (easiest):**
- **Chrome/Edge**: Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox**: Install [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
- Visit `youtube.com`, click the extension icon, export as **Netscape format**
- Save to: `~/Documents/MyYouTube/cookies.txt`

**Option B — Export via yt-dlp:**
```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ~/Documents/MyYouTube/cookies.txt \
       --skip-download "https://www.youtube.com"
```

Then set in `MyYouTube.yaml`:
```yaml
cookies_file: ~/Documents/MyYouTube/cookies.txt
```

### Method 2: Live Browser Session (Fallback)

Set `cookies_file: null` and configure your browser:
```yaml
cookies_file: null
browser: chrome   # or firefox, brave, edge
```

You must be **logged into YouTube** in that browser.

> **macOS Note**: Safari is sandboxed and usually blocked. Use Chrome, Firefox, or Brave.

### Quick Help

```bash
myt --cookies-help   # show full setup instructions
```

## Local Library

When you save a video or audio, MyYouTube stores:
- The media file in `video_dir` or `audio_dir`
- A `.info.json` sidecar with full metadata (title, description, thumbnails, etc.)

The Library page reads these sidecar files to display info and allow playback without re-fetching from YouTube.

## Architecture

```
myt                    Python entry point
src/
  app.py               Page stack router
  config.py            Config management
  ytdlp.py             All yt-dlp interactions
  cache.py             Disk cache with TTL
  library.py           Local library DB
  history.py           Watch history
  player.py            mpv IPC controller
  deps.py              Dependency checker
  ui/
    fzf.py             fzf wrapper
    gum.py             gum wrapper
    thumbnail.py       chafa rendering
    pages/             One file per page
MyYouTube.yaml         User configuration
```

## Troubleshooting

**"Operation not permitted" with Safari cookies**
→ Use `browser: chrome` or `firefox` in your config.

**mpv fails with dylib error**
→ Run `brew reinstall ffmpeg && brew reinstall mpv`

**Home feed returns no results**
→ Make sure you're logged into YouTube in your configured browser. The recommended feed requires an active session.

**Thumbnails look bad**
→ Try a terminal that supports sixel graphics (iTerm2, WezTerm, Kitty). chafa auto-detects the best protocol.
