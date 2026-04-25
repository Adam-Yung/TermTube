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
| `` ` `` | Open quick-navigation pages picker |
| `q` | Quit |

## Dependencies

TermTube relies on a few core system utilities:

| Tool | Purpose | Install |
|------|---------|---------|
| `yt-dlp` | YouTube engine | `brew install yt-dlp` |
| `mpv` | Video/audio playback | `brew install mpv` |
| `chafa` | Terminal thumbnails (optional) | `brew install chafa` |
| `ffmpeg` | Audio conversion (optional) | `brew install ffmpeg` |
| Python 3.11+ | Runtime | `brew install python@3.11` |

## Installation

TermTube uses `setup.sh` to create a clean `venv` environment and optionally add the `termtube` command to your PATH.

```bash
git clone --depth 1 https://github.com/yourname/termtube.git ~/termtube
cd ~/termtube
bash setup.sh
```

For **development** (edits take effect immediately, no re-install needed):

```bash
bash setup.sh --sync
```

Run `bash setup.sh --help` for full options.

*(To remove TermTube: `termtube --uninstall`)*

## Configuration

Config lives at `~/.config/TermTube/config.yaml` and is created automatically on first run. Key settings:

```yaml
browser: chrome              # Browser for YouTube cookies (chrome/firefox/brave/edge)
cookies_file: ~/.config/TermTube/cookies.txt
video_dir: ~/Documents/TermTube/Video
audio_dir: ~/Documents/TermTube/Audio
preferred_quality: best      # best | 720 | 1080 | 4k
preferred_player: mpv
theme: crimson               # crimson | amber | ocean | midnight
cache_ttl:
  home: 3600                 # seconds
  subscriptions: 3600
  search: 1800
  metadata: 86400
```

## Cookie Setup (Required for Home Feed & Subscriptions)

TermTube needs your YouTube session cookies to fetch your personalized home feed and subscriptions.

**Option A — Export via yt-dlp (recommended):**
```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ~/.config/TermTube/cookies.txt \
       --skip-download --quiet --no-warnings \
       "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```
Replace `chrome` with `firefox`, `brave`, or `edge` as needed.

**Option B — Browser extension:**
1. Install "Get cookies.txt LOCALLY" (Chrome) or "cookies.txt" (Firefox).
2. Visit `youtube.com`, click the extension, export as **Netscape format**.
3. Save to `~/.config/TermTube/cookies.txt`.

**Option C — Browser session (no file):**
Set `cookies_file: null` and `browser: chrome` in your config. TermTube will read cookies directly from the running browser. Safari is sandboxed on macOS and usually blocked.

## Architecture

TermTube is a native Python application built on `Textual`. All network I/O runs in background threads — the UI never blocks. Feed data streams lazily from `yt-dlp`, and a stale-while-revalidate cache ensures cold starts are instant.

For full architectural details and AI agent contribution instructions, see `CLAUDE.md`.
