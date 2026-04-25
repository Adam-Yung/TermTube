# TermTube — Claude Instructions

## Project Overview
A YouTube TUI wrapper using Python + fzf + gum + chafa + mpv + yt-dlp.
Python orchestrates all logic and state. fzf drives interactive list UIs. gum handles prompts/spinners/styling.

## Architecture
```
termtube                    # executable entry point (chmod +x, Python shebang)
src/
  app.py               # main router/page stack state machine
  config.py            # YAML config (PyYAML), reads/writes TermTube.yaml
  ytdlp.py             # yt-dlp subprocess interface, feed fetching
  cache.py             # disk cache (~/.cache/termtube/) with TTL
  library.py           # local saved-video DB (JSON sidecar files)
  history.py           # local watch history (JSON, separate from YouTube history)
  player.py            # mpv IPC controller (--input-ipc-server)
  deps.py              # dependency checker + install prompts
  ui/
    fzf.py             # fzf subprocess wrapper (build --preview, --bind, etc.)
    gum.py             # gum subprocess wrapper (spinner, choose, input, style)
    thumbnail.py       # chafa image rendering for fzf preview
    pages/
      home.py          # /feed/recommended via yt-dlp + cookies
      search.py        # yt-dlp search
      subscriptions.py # /feed/subscriptions via yt-dlp + cookies
      library.py       # local saved files
      history.py       # local watch history + yt-dlp /feed/history
      video_detail.py  # single video view with actions menu
TermTube.yaml         # user config (auto-created on first run)
requirements.txt       # PyYAML, requests (minimal deps)
```

## Key Design Decisions
- **Language**: Python 3.11 (termtube mamba env) as orchestrator; shell tools for UI
- **fzf**: Used for all interactive list views. `--preview` runs `src/ui/preview.py {1} {cols} {rows}` (video_id as first tab-delimited field)
- **gum**: spin_while() for loading animation, choose() for action menus, text_input() for search
- **Thumbnails**: Downloaded to `~/.cache/termtube/thumbs/{id}.jpg`, rendered with chafa
- **Navigation**: App.run() loops showing main menu → routes to page fn → page returns video_id or None → None goes back to menu
- **mpv**: Launched with `--input-ipc-server=/tmp/termtube-mpv.sock` + temp input.conf with custom seek bindings
- **Cookie priority**: `cookies_file` (path to Netscape cookies.txt) checked FIRST; falls back to `--cookies-from-browser {browser}`. See Config.cookie_args property.
- **Cache**: `~/.cache/termtube/` — videos/{id}.json, thumbs/{id}.jpg, feed_{key}.json
- **Library**: `--write-info-json` sidecar files alongside downloaded media. library.py scans for *.info.json
- **History**: `~/.local/share/termtube/history.json` — LOCAL only (TUI watch history, NOT Google account)

## Progressive Loading (Key Feature)
1. `yt-dlp --flat-playlist --dump-json --extractor-args youtube:skip=dash,hls URL` streams JSON lines
2. `fzf.run_list()` calls `_wait_for_first()` which animates a spinner until first entry arrives
3. Once first entry appears, fzf subprocess is started; entries written to fzf stdin as they arrive
4. fzf preview pane (`src/ui/preview.py`) reads from `~/.cache/termtube/videos/{id}.json` (always fast)
5. Background enrichment via `ytdlp.enrich_in_background()` can fetch full metadata in parallel

## Environment (macOS)
- Tools available: yt-dlp (2026.03.17), fzf, mpv, chafa, jq, ffmpeg, gum, python3 (3.13.12)
- mamba env: `termtube` at /Users/adyung/miniforge3/envs/termtube (Python 3.11)
- Entry point: `./termtube` shell wrapper → finds termtube env → runs src/main.py
- NOTE: mpv has a broken x265 dylib → `brew reinstall ffmpeg` may be needed. mpv can still play via yt-dlp without local ffmpeg for most formats.
- Safari cookies: macOS sandboxes Safari. Recommend Chrome/Firefox/Brave as default browser option.

## yt-dlp Feed URLs
- Home/Recommended: `https://www.youtube.com/feed/recommended`
- Subscriptions: `https://www.youtube.com/feed/subscriptions`
- History: `https://www.youtube.com/feed/history`
- Search: `ytsearch50:{query}` or `https://www.youtube.com/results?search_query={query}`

## mpv Input Bindings (custom input.conf)
```
0 seek 0 absolute-percent
1 seek 10 absolute-percent
... 9 seek 90 absolute-percent
h seek -5
l seek +5
H seek -10
L seek +10
LEFT seek -5
RIGHT seek +5
Ctrl+LEFT seek -10
Ctrl+RIGHT seek +10
```

## Config File (TermTube.yaml) Schema
```yaml
browser: chrome        # for yt-dlp cookies-from-browser
video_dir: ~/Documents/TermTube/Video
audio_dir: ~/Documents/TermTube/Audio
video_format: "%(title)s_%(uploader)s.%(ext)s"
audio_format: "%(title)s_%(uploader)s.%(ext)s"
preferred_quality: best  # or 720, 1080, etc.
preferred_player: mpv    # or vlc
cache_ttl:
  home: 3600
  subscriptions: 3600
  search: 1800
  metadata: 86400
thumbnail_width: 40      # chars wide in fzf preview
```

## Code Conventions
- Python: type hints, f-strings, pathlib.Path for all paths
- All yt-dlp calls go through `src/ytdlp.py` — never call yt-dlp directly from pages
- All fzf calls go through `src/ui/fzf.py`
- All gum calls go through `src/ui/gum.py`
- Never block the main thread during network I/O — use subprocess with timeout
- Error handling: always show user-friendly gum error, never traceback in production

## Files to Update When Making Changes
- Always update `CLAUDE.md` (this file) if architecture changes
- Always update `memory/MEMORY.md` with new decisions/learnings
- Update `README.md` for user-visible changes
- Update `TermTube.yaml` schema docs if config keys change
