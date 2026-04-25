# TermTube

A blazing fast, purely native Python TUI for YouTube. Built on the `Textual` framework, it offers a seamless, reactive interface right in your terminal, complete with high-res thumbnails, embedded audio playback, and instant feed loading.

## Features

- **Lightning Fast UI** — Native Python interface with zero shell-wrapper overhead.
- **Smart Home Feed** — Instantly loads via cache, automatically filtering out stale videos you've already scrolled past or watched using LRU memory tracking.
- **Background Audio** — Listen to YouTube audio in the background while browsing, controlled via an embedded TUI action bar.
- **High-Res Thumbnails** — Native support for Sixel and Kitty graphics protocols, falling back to beautiful `chafa` ANSI block renderings if unsupported.
- **Full Ecosystem** — Home feeds, Subscriptions, Search, Library, History, and custom local Playlists.
- **Watch & Save** — Suspend the TUI to watch videos cleanly in `mpv`, or download streams locally (Video/Audio) with metadata sidecars.

## Navigation

| Key | Action |
|-----|--------|
| `↑↓` / `jk` | Move up/down in list |
| `l` / `h` | Seek ±5s in embedded audio player (or `l` to start listening) |
| `L` / `H` | Seek ±10s in embedded audio player |
| `w` | Watch video in external player |
| `0`–`9` | Seek to 0%–90% of media |
| `Enter` | Open detailed actions menu for selected video |
| `/` | Search YouTube |
| `\`` | Open quick-navigation pages picker |
| `q` | Quit |

## Dependencies

TermTube relies on a few core system utilities:

| Tool | Purpose | Install |
|------|---------|---------|
| `yt-dlp` | YouTube engine | `brew install yt-dlp` |
| `mpv` | Video/audio playback | `brew install mpv` |
| `chafa` | Terminal thumbnails | `brew install chafa` |
| Python 3.11+ | Orchestration | `brew install python3` |

## Installation

TermTube uses a setup script to create a clean, isolated environment in `~/.local/share/TermTube` and adds a symlink to your path.

```bash
git clone --depth 1 [https://github.com/yourname/termtube.git](https://github.com/yourname/termtube.git) /tmp/termtube
cd /tmp/termtube
bash setup.sh
```

*(To completely remove TermTube from your system later, simply run `termtube --uninstall`)*

## Configuration

On first run, `TermTube.yaml` is generated in `~/.config/termtube/`. Key settings:

```yaml
browser: chrome            # Browser for YouTube session cookies (used by yt-dlp)
video_dir: ~/Documents/TermTube/Video
audio_dir: ~/Documents/TermTube/Audio
preferred_quality: best    # Options: best, 720, 1080, 4k
preferred_player: mpv      # Options: mpv, vlc
cache_ttl:
  home: 3600               # 1 hour
  subscriptions: 3600
```

## Cookie Setup (Required for Home Feed)

TermTube needs your YouTube session cookies to fetch your personalized home feed and subscriptions. **Using a `cookies.txt` file is highly recommended** for performance.

**Export via browser extension (easiest):**
1. Install an extension like "Get cookies.txt LOCALLY" for your browser.
2. Visit `youtube.com`, click the extension, and export as **Netscape format**.
3. Save to `~/Documents/TermTube/cookies.txt`.
4. Update your `TermTube.yaml` to point to it: `cookies_file: ~/Documents/TermTube/cookies.txt`

*(Fallback: If `cookies_file: null` is set, TermTube will attempt to extract cookies directly from the browser specified in your config. Note: macOS sandboxes Safari, so use Chrome, Brave, or Firefox).*

## Architecture

TermTube is a native Python application utilizing `Textual`. Network interactions are handled asynchronously via background workers, meaning the UI never blocks while fetching videos or thumbnails. 

For full architectural details and contribution instructions, see `CLAUDE.md`.

