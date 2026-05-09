#!/usr/bin/env bash
# TermTube v2 — Cross-platform install script.
#
# Supports macOS (brew) and Linux (apt/dnf/pacman auto-detected).
# Flags: --sync (dev mode), --no-deps (skip system deps), --help

set -euo pipefail

# ── Argument Parsing ───────────────────────────────────────────────────────
SYNC_MODE=false
SKIP_DEPS=false

for arg in "$@"; do
    case "$arg" in
        --sync)    SYNC_MODE=true ;;
        --no-deps) SKIP_DEPS=true ;;
        --help|-h)
            cat <<'EOF'

  TermTube v2 — Setup Script
  ═══════════════════════════

  Usage: bash setup.sh [OPTIONS]

  Options:
    (no flags)   Copy project to ~/.local/share/TermTube and install there.
                 Good for end-user installs.

    --sync       Symlink ~/.local/share/TermTube → current directory.
                 Use for development: edits are immediately live.
                 The .venv is kept inside the repo.

    --no-deps    Skip system dependency installation (mpv, ffmpeg).
                 Only set up the Python venv and install Python packages.

    --help, -h   Show this help message and exit.

  What it does:
    1. Detects your OS (macOS / Linux) and package manager
    2. Checks for Python 3.11+ (offers to install if missing)
    3. Installs mpv and ffmpeg if absent (unless --no-deps)
    4. Creates a Python venv and installs all pip dependencies
    5. Creates ~/.local/bin/termtube symlink
    6. Idempotent — safe to re-run at any time

  Paths:
    App install:   ~/.local/share/TermTube/
    Config:        ~/.config/TermTube/config.yaml
    Cookies:       ~/.config/TermTube/cookies.txt
    Cache:         ~/.cache/termtube/
    CLI command:   ~/.local/bin/termtube

EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $arg (try --help)" >&2
            exit 1
            ;;
    esac
done

# ── Paths ──────────────────────────────────────────────────────────────────
ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/TermTube"
BIN_DIR="$HOME/.local/bin"
BIN_FALLBACK="$HOME/bin"
CONFIG_DIR="$HOME/.config/TermTube"

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── OS & Package Manager Detection ────────────────────────────────────────
detect_os() {
    local uname_out
    uname_out="$(uname -s)"
    case "$uname_out" in
        Darwin*) OS="macos" ;;
        Linux*)  OS="linux" ;;
        *)       OS="unknown" ;;
    esac
}

detect_pkg_manager() {
    PKG_MANAGER=""
    PKG_INSTALL=""
    if [[ "$OS" == "macos" ]]; then
        if command -v brew &>/dev/null; then
            PKG_MANAGER="brew"
            PKG_INSTALL="brew install"
        fi
    elif [[ "$OS" == "linux" ]]; then
        if command -v apt-get &>/dev/null; then
            PKG_MANAGER="apt"
            PKG_INSTALL="sudo apt-get install -y"
        elif command -v dnf &>/dev/null; then
            PKG_MANAGER="dnf"
            PKG_INSTALL="sudo dnf install -y"
        elif command -v pacman &>/dev/null; then
            PKG_MANAGER="pacman"
            PKG_INSTALL="sudo pacman -S --noconfirm"
        elif command -v zypper &>/dev/null; then
            PKG_MANAGER="zypper"
            PKG_INSTALL="sudo zypper install -y"
        fi
    fi
}

# ── Python Detection ──────────────────────────────────────────────────────
find_python() {
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" &>/dev/null; then
            local ver
            ver=$("$candidate" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "0.0")
            local major minor
            major="${ver%%.*}"
            minor="${ver#*.}"
            if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
                PYTHON="$candidate"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    header "Python 3.11+ not found — attempting to install…"
    if [[ "$OS" == "macos" && -n "$PKG_INSTALL" ]]; then
        info "Installing python@3.12 via brew…"
        $PKG_INSTALL python@3.12
    elif [[ "$OS" == "linux" ]]; then
        case "$PKG_MANAGER" in
            apt)    info "Installing python3.11…"; $PKG_INSTALL python3.11 python3.11-venv ;;
            dnf)    info "Installing python3.11…"; $PKG_INSTALL python3.11 ;;
            pacman) info "Installing python…"; $PKG_INSTALL python ;;
            *)      return 1 ;;
        esac
    else
        return 1
    fi
    find_python
}

# ── System Dependencies ───────────────────────────────────────────────────
install_system_deps() {
    if [[ "$SKIP_DEPS" == true ]]; then
        info "Skipping system dependency check (--no-deps)"
        return 0
    fi

    header "Checking system dependencies…"

    # mpv (required)
    if command -v mpv &>/dev/null; then
        success "mpv found: $(mpv --version 2>/dev/null | head -1)"
    else
        if [[ -n "$PKG_INSTALL" ]]; then
            info "Installing mpv…"
            $PKG_INSTALL mpv
            success "mpv installed"
        else
            warn "mpv not found. Install manually: https://mpv.io/installation/"
        fi
    fi

    # ffmpeg (optional but recommended)
    if command -v ffmpeg &>/dev/null; then
        success "ffmpeg found: $(ffmpeg -version 2>/dev/null | head -1)"
    else
        if [[ -n "$PKG_INSTALL" ]]; then
            info "Installing ffmpeg…"
            $PKG_INSTALL ffmpeg
            success "ffmpeg installed"
        else
            warn "ffmpeg not found (optional — improves format muxing)"
        fi
    fi
}

# ── Venv Setup ────────────────────────────────────────────────────────────
setup_venv() {
    local venv_dir="$1"
    local req_file="$2"

    header "Setting up Python virtual environment…"

    if [[ -d "$venv_dir" ]]; then
        info "Existing venv found at $venv_dir — upgrading packages…"
    else
        info "Creating venv at $venv_dir…"
        "$PYTHON" -m venv "$venv_dir"
    fi

    # Upgrade pip silently
    "$venv_dir/bin/pip" install --quiet --upgrade pip

    # Install all requirements (yt-dlp as Python package for latest version)
    info "Installing Python packages from requirements.txt…"
    "$venv_dir/bin/pip" install --quiet -r "$req_file"
    success "Python packages installed"
}

# ── Create CLI symlink ────────────────────────────────────────────────────
install_symlink() {
    local target_dir="$BIN_DIR"

    # Fallback to ~/bin if ~/.local/bin doesn't exist and isn't in PATH
    if [[ ! -d "$BIN_DIR" ]] && [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        if [[ -d "$BIN_FALLBACK" ]] || [[ ":$PATH:" == *":$BIN_FALLBACK:"* ]]; then
            target_dir="$BIN_FALLBACK"
        fi
    fi

    mkdir -p "$target_dir"
    ln -sf "$APP_DIR/termtube" "$target_dir/termtube"

    if [[ ":$PATH:" != *":$target_dir:"* ]]; then
        warn "$target_dir is not in your PATH."
        info "Add to your shell profile (~/.zshrc or ~/.bashrc):"
        echo -e "  ${CYAN}export PATH=\"$target_dir:\$PATH\"${RESET}"
    else
        success "CLI installed: ${target_dir}/termtube"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

echo -e "${BOLD}TermTube v2 — Setup${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

detect_os
detect_pkg_manager

info "Detected OS: ${BOLD}$OS${RESET}"
if [[ -n "$PKG_MANAGER" ]]; then
    info "Package manager: ${BOLD}$PKG_MANAGER${RESET}"
fi

# ── Step 1: Python ─────────────────────────────────────────────────────────
header "Checking Python…"
if find_python; then
    success "Python found: $($PYTHON --version)"
else
    if ! install_python; then
        error "Python 3.11+ is required but could not be found or installed."
        error "Install manually:"
        if [[ "$OS" == "macos" ]]; then
            error "  brew install python@3.12"
        else
            error "  sudo apt install python3.11 python3.11-venv"
        fi
        exit 1
    fi
    success "Python installed: $($PYTHON --version)"
fi

# ── Step 2: System deps ───────────────────────────────────────────────────
install_system_deps

# ── Step 3: Copy / Sync ───────────────────────────────────────────────────
if [[ "${ORIG_DIR}" == "${APP_DIR}" ]]; then
    info "Already running from install directory."
elif [[ "$SYNC_MODE" == true ]]; then
    header "Setting up development sync mode…"
    rm -rf "$APP_DIR"
    ln -s "$ORIG_DIR" "$APP_DIR"
    success "Symlinked $APP_DIR → $ORIG_DIR"
    info "Edits in $ORIG_DIR are immediately live."
else
    # Interactive prompt for sync mode
    echo ""
    read -r -p "Install in sync mode for development? [y/N] " reply
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        SYNC_MODE=true
        rm -rf "$APP_DIR"
        ln -s "$ORIG_DIR" "$APP_DIR"
        success "Symlinked $APP_DIR → $ORIG_DIR"
    else
        header "Copying files for production install…"
        rm -rf "$APP_DIR"
        mkdir -p "$APP_DIR"
        # Copy essential files
        cp -a "$ORIG_DIR/src" "$APP_DIR/"
        for f in requirements.txt termtube setup.sh uninstall.sh; do
            [[ -f "$ORIG_DIR/$f" ]] && cp -a "$ORIG_DIR/$f" "$APP_DIR/"
        done
        # Copy memory dir for AI agent context
        [[ -d "$ORIG_DIR/memory" ]] && cp -a "$ORIG_DIR/memory" "$APP_DIR/"
        chmod +x "$APP_DIR/termtube" "$APP_DIR/setup.sh" "$APP_DIR/uninstall.sh" 2>/dev/null || true
        success "Copied project to $APP_DIR"
    fi
fi

# ── Step 4: Python venv ───────────────────────────────────────────────────
VENV_DIR="$APP_DIR/.venv"
REQUIREMENTS="$APP_DIR/requirements.txt"

if [[ ! -f "$REQUIREMENTS" ]]; then
    error "requirements.txt not found at $REQUIREMENTS"
    exit 1
fi

setup_venv "$VENV_DIR" "$REQUIREMENTS"

# ── Step 5: Config directory ──────────────────────────────────────────────
if [[ ! -d "$CONFIG_DIR" ]]; then
    mkdir -p "$CONFIG_DIR"
    info "Created config directory: $CONFIG_DIR"
fi

# ── Step 6: CLI symlink ───────────────────────────────────────────────────
header "Installing CLI command…"
install_symlink

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}Setup complete!${RESET}"
echo ""
echo -e "  ${BOLD}Run:${RESET}     termtube"
echo -e "  ${BOLD}Config:${RESET}  $CONFIG_DIR/config.yaml"
echo -e "  ${BOLD}Cache:${RESET}   ~/.cache/termtube/"
echo ""
if [[ "$SYNC_MODE" == true ]]; then
    echo -e "  ${DIM}Mode: development (sync)${RESET}"
else
    echo -e "  ${DIM}Mode: production (copy)${RESET}"
fi
echo ""
