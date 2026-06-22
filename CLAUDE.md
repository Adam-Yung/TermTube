# TermTube — AI Agent Instructions

## Project Overview
TermTube is a native Python TUI for YouTube. It utilizes the `Textual` framework for the UI, `yt-dlp` for data extraction, `mpv` for media playback (via IPC), and `textual-image`/PIL for terminal graphics.

**Core philosophy:** Lightning-fast cold starts, non-blocking asynchronous UI, and a native terminal feel without relying on shell wrappers (fzf/gum are deprecated).

## Project Structure
```text
termtube                    # Executable entry point (resolves .venv, runs main.py — auto-installs on first run)
termtube.cmd                # Windows launcher (same logic, cmd batch)
scripts/
  setup.sh                  # Installation script (macOS/Linux)
  setup.ps1                 # Installation script (Windows)
  uninstall.sh              # Uninstaller (macOS/Linux)
  uninstall.ps1             # Uninstaller (Windows)
assets/
  termtube.png              # Brand image
  termtube.icns             # macOS app icon (multi-resolution)
  termtube.ico              # Windows shortcut icon (multi-resolution)
src/
  main.py                   # App launch script
  config.py                 # PyYAML configuration manager (~/.config/TermTube/config.yaml)
  ytdlp.py                  # yt-dlp API wrapper (streams JSON lazily)
  cache.py                  # Disk + RAM cache (LRU suppression, stale-while-revalidate)
  library.py                # Local saved-video DB manager
  history.py                # Local watch history manager
  player.py                 # mpv IPC controller (--input-ipc-server)
  plat.py                   # Platform abstraction layer (paths, IPC, clipboard, process mgmt)
  bootstrap.py              # Binary dependency installer (downloads from GitHub releases)
  deps.py                   # Dependency validation + bootstrap prompt
  updater.py                # Tool updater + app-code self-update via GitHub releases
  tests/                    # Test suite (unit, integration, tui, snapshots)
  tui/
    app.py                  # Textual App root (TermTubeApp)
    theme.tcss              # App styling
    screens/                # Textual Screens (Main, Modals)
    widgets/                # Custom Textual Widgets (VideoList, DetailPanel, Thumbnails)
memory/                     # AI agent session memory (architecture decisions, active context)
```
memory/                     # AI agent session memory (architecture decisions, active context)
```

## File Locations at Runtime
| File | Path |
|------|------|
| Config | `~/.config/TermTube/config.yaml` |
| Cookies | `~/.config/TermTube/cookies.txt` |
| App install | `~/.local/share/TermTube/` |
| CLI symlink | `~/.local/bin/termtube` |
| Python env | `<install_dir>/.venv/` |
| Thumbnails/cache | `~/.cache/termtube/` (managed by cache.py) |
| Binary deps | `~/.local/termtube-deps/bin/` (managed by bootstrap.py) |

## Key Technical Decisions
- **Framework**: Pure `Textual`. No shell subprocesses for UI (no fzf/gum).
- **Python environment**: `venv` only. No conda/mamba. Chosen for portability and zero external toolchain dependencies.
- **State & Concurrency**: Network I/O must use `@work(thread=True, exclusive=True)`. Update UI safely from threads using `self.app.call_from_thread()`. Decouple components using Textual `Message` classes.
- **Lazy Loading**: `yt-dlp` streams JSON directly to a buffer. `VideoListPanel` renders items in small batches on scroll.
- **Caching & Suppression**: Home feed boots instantly from disk cache. A background worker refreshes it every 10 mins. Videos focused 3+ times or watched are added to an LRU suppression list and hidden from future home feeds.
- **Media Playback**:
  - **Audio**: `mpv` runs headlessly via socket IPC (`/tmp/termtube-mpv-audio.sock`).
  - **Video**: Uses `app.suspend()` to yield the terminal to `mpv`, restoring the TUI upon exit.
- **Thumbnails**: Uses `textual-image` (Sixel/Kitty graphics) falling back to PIL half-block (24-bit ANSI color). Downloads happen in background workers.
- **Config**: Single source of truth at `~/.config/TermTube/config.yaml`. Created automatically on first save. No config file ships in the repo.
- **yt-dlp Integration**: yt-dlp is installed as a Python library (`pip install yt-dlp yt-dlp-ejs`) in the app's venv. It is imported directly (`import yt_dlp`) — no subprocess spawning. The `yt-dlp-ejs` package provides YouTube JS challenge solver scripts. A JS runtime (Deno) is still needed and is managed as a binary dependency.
- **Bundled Dependencies**: Binary deps (deno, ffmpeg, mpv) are downloaded from GitHub releases into `~/.local/termtube-deps/bin/` (or `%LOCALAPPDATA%\termtube-deps\bin\` on Windows) by `src/bootstrap.py`. This directory is prepended to PATH at app startup. **Always prefer the bundled binaries over system-installed versions.** This gives us full control over versions and updates, and prevents silent breakage if a user removes a system package. Never fall back to or prefer system PATH versions over our managed copies.

---

## Setup Modes
- **`bash scripts/setup.sh`** — copies project to `~/.local/share/TermTube`, creates `.venv` there.
- **`.\scripts\setup.ps1`** — Windows equivalent. Creates `.venv` at `%LOCALAPPDATA%\Programs\TermTube\.venv`.
- **First-run auto-install**: running `./termtube` or `.\termtube.cmd` from a fresh clone automatically runs the appropriate setup script with `--no-prompt`.

---

## 🤖 AI Agent Directives (STRICT)

To minimize token usage and maintain project coherence, all AI agents modifying this codebase MUST adhere to the following rules:

### 1. Memory Tracking (`memory/` directory)
You must maintain a `memory/` folder in the root directory to track context across sessions. This prevents repetitive prompt explanations and saves tokens.
- **Create/Update `memory/architecture_decisions.md`**: Document *why* a technical approach was taken (e.g., "Why we use IPC for mpv instead of subprocess blocking").
- **Create/Update `memory/active_context.md`**: Briefly log the current active task or bug being worked on. Clear this when a task is completed.

### 2. Documentation Enforcement
Whenever you implement a new feature, fix a bug, or change the architecture, you MUST update the following files if applicable:
- `README.md` (for user-facing changes, features, or new dependencies).
- `ROADMAP.md` (move items from Planned -> Done).
- `CLAUDE.md` (this file, if core architecture, structure, or rules change).
- `~/.config/TermTube/config.yaml` is the user's live config — never modify it from code except through `Config.save()`.

### 3. Code Generation Rules
- **No dead code:** Clean up deprecated functions immediately.
- **Non-blocking UI:** Never block the main Textual thread.
- **Type hinting:** Use Python 3.11+ type hints (`list[str]`, `| None`, etc.).
- **File context:** When providing code solutions, output the full file contents unless an explicit diff/snippet is requested, to prevent partial-update errors.
- **No conda/mamba:** All environment management uses Python `venv` only.
