# TermTube — AI Agent Instructions

## Project Overview
TermTube is a native Python TUI for YouTube. It utilizes the `Textual` framework for the UI, `yt-dlp` for data extraction, `mpv` for media playback (via IPC), and `textual-image`/`chafa` for terminal graphics. 

**Core philosophy:** Lightning-fast cold starts, non-blocking asynchronous UI, and a native terminal feel without relying on shell wrappers (fzf/gum are deprecated).

## Project Structure
```text
termtube                    # Executable entry point (resolves venv, runs main.py)
setup.sh                    # Installation script (~/.local/share/TermTube persistence)
uninstall.sh                # Uninstaller script
src/
  main.py                   # App launch script
  config.py                 # PyYAML configuration manager
  ytdlp.py                  # yt-dlp API wrapper (streams JSON lazily)
  cache.py                  # Disk + RAM cache (LRU suppression, stale-while-revalidate)
  library.py                # Local saved-video DB manager
  history.py                # Local watch history manager
  player.py                 # mpv IPC controller (--input-ipc-server)
  deps.py                   # Dependency validation
  tui/
    app.py                  # Textual App root (TermTubeApp)
    theme.tcss              # App styling
    screens/                # Textual Screens (Main, Modals)
    widgets/                # Custom Textual Widgets (VideoList, DetailPanel, Thumbnails)
```

## Key Technical Decisions
- **Framework**: Pure `Textual`. No shell subprocesses for UI (no fzf/gum).
- **State & Concurrency**: Network I/O must use `@work(thread=True, exclusive=True)`. Update UI safely from threads using `self.app.call_from_thread()`. Decouple components using Textual `Message` classes.
- **Lazy Loading**: `yt-dlp` streams JSON directly to a buffer. `VideoListPanel` renders items in small batches on scroll.
- **Caching & Suppression**: Home feed boots instantly from disk cache. A background worker refreshes it every 10 mins. Videos focused 3+ times or watched are added to an LRU suppression list and hidden from future home feeds.
- **Media Playback**: 
  - **Audio**: `mpv` runs headlessly via socket IPC (`/tmp/termtube-mpv-audio.sock`). 
  - **Video**: Uses `app.suspend()` to yield the terminal to `mpv`, restoring the TUI upon exit.
- **Thumbnails**: Uses `textual-image` (Sixel/Kitty graphics) falling back to `chafa` (ANSI blocks). Downloads happen in background workers.

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
- `TermTube.yaml` (if adding new config keys).

### 3. Code Generation Rules
- **No dead code:** Clean up deprecated functions immediately.
- **Non-blocking UI:** Never block the main Textual thread.
- **Type hinting:** Use Python 3.11+ type hints (`list[str]`, `| None`, etc.).
- **File context:** When providing code solutions, output the full file contents unless an explicit diff/snippet is requested, to prevent partial-update errors.
