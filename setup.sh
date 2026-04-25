#!/usr/bin/env bash
# TermTube setup — creates a Python venv and installs dependencies.

set -euo pipefail

# ── Argument Parsing ───────────────────────────────────────────────────────
SYNC_MODE=false
for arg in "$@"; do
    case "$arg" in
        --sync)   SYNC_MODE=true ;;
        --help|-h)
            echo ""
            echo "  TermTube Setup Script"
            echo ""
            echo "  Usage: bash setup.sh [OPTIONS]"
            echo ""
            echo "  Options:"
            echo "    (no flags)   Copy project to ~/.local/share/TermTube and install there."
            echo "                 Good for normal end-user installs. Changes to the source"
            echo "                 directory are NOT reflected without re-running setup.sh."
            echo ""
            echo "    --sync       Symlink ~/.local/share/TermTube → current directory."
            echo "                 Use this for development: edits in the source directory"
            echo "                 are immediately live, and the .venv is kept inside the"
            echo "                 repo so it survives re-runs."
            echo ""
            echo "    --help, -h   Show this help message and exit."
            echo ""
            echo "  Configuration:"
            echo "    Config file:  ~/.config/TermTube/config.yaml  (created on first run)"
            echo "    Cookies file: ~/.config/TermTube/cookies.txt  (add manually)"
            echo ""
            echo "  System dependencies (install separately):"
            echo "    brew install yt-dlp mpv chafa ffmpeg"
            echo ""
            exit 0
            ;;
    esac
done

ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/TermTube"
BIN_DIR="$HOME/.local/bin"

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── Helpers ────────────────────────────────────────────────────────────────

pip_install() {
    local pip_bin="$1"
    info "Installing Python dependencies from requirements.txt…"
    grep -v '^\s*#' "${REQUIREMENTS}" | grep -v '^\s*$' | \
        "$pip_bin" install --quiet -r /dev/stdin
    success "Dependencies installed."
}

check_python_version() {
    local py="$1"
    local ver
    ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    python3 -c "import sys; sys.exit(0 if tuple(map(int,'$ver'.split('.'))) >= (3,11) else 1)" 2>/dev/null
}

# ── Set up Python venv ─────────────────────────────────────────────────────

setup_venv() {
    header "Setting up Python venv (.venv/)"

    local py=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" &>/dev/null && check_python_version "$candidate"; then
            py="$candidate"
            break
        fi
    done

    if [[ -z "$py" ]]; then
        error "No Python >= 3.11 found. Install it with:"
        error "  macOS:  brew install python@3.11"
        error "  Linux:  sudo apt install python3.11"
        return 1
    fi

    local ver
    ver=$("$py" --version 2>&1)
    info "Using $ver"

    if [[ -d "${VENV_DIR}" ]]; then
        info "Virtual environment already exists at ${VENV_DIR} — updating…"
    else
        info "Creating virtual environment at ${VENV_DIR}…"
        "$py" -m venv "${VENV_DIR}"
    fi

    pip_install "${VENV_DIR}/bin/pip"
    success "Virtual environment ready at ${VENV_DIR}"
    return 0
}

# ── Main ───────────────────────────────────────────────────────────────────

echo -e "${BOLD}TermTube Setup${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Persistence / Copy / Sync
if [[ "${ORIG_DIR}" != "${APP_DIR}" ]]; then
    if [[ "${SYNC_MODE}" == true ]]; then
        header "Symlinking for development sync…"
        # Remove existing (directory or symlink) then create a single symlink
        rm -rf "${APP_DIR}"
        ln -s "${ORIG_DIR}" "${APP_DIR}"
        success "Symlinked ${APP_DIR} → ${ORIG_DIR}"
        info "Edits in ${ORIG_DIR} are immediately live. .venv lives inside your repo."
    else
        header "Copying files for persistent installation…"
        rm -rf "${APP_DIR}"
        mkdir -p "${APP_DIR}"

        if [[ -d "${ORIG_DIR}/src" ]]; then
            cp -a "${ORIG_DIR}/src" "${APP_DIR}/"
        fi

        for f in requirements.txt termtube setup.sh uninstall.sh theme.tcss; do
            if [[ -f "${ORIG_DIR}/$f" ]]; then
                cp -a "${ORIG_DIR}/$f" "${APP_DIR}/"
            fi
        done

        chmod +x "${APP_DIR}/termtube" "${APP_DIR}/setup.sh" "${APP_DIR}/uninstall.sh"
        success "Copied project files to ${APP_DIR}"
    fi
fi

# APP_DIR is either a real directory (copy mode) or a symlink to ORIG_DIR (sync mode)
SCRIPT_DIR="${APP_DIR}"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_MIN="3.11"

# Check system dependencies (non-fatal warnings)
header "Checking system tools…"
for tool in yt-dlp mpv; do
    if command -v "$tool" &>/dev/null; then
        success "$tool found ($(command -v "$tool"))"
    else
        warn "$tool not found — install with: brew install $tool"
    fi
done
for tool in chafa ffmpeg; do
    if command -v "$tool" &>/dev/null; then
        success "$tool found"
    else
        warn "$tool not found (optional) — brew install $tool"
    fi
done

# Set up Python venv
header "Setting up Python environment…"
setup_venv || {
    error "Could not create a Python environment."
    error "Install Python >= 3.11 and try again:  brew install python@3.11"
    exit 1
}

# Ensure config directory exists
CONFIG_DIR="$HOME/.config/TermTube"
if [[ ! -d "${CONFIG_DIR}" ]]; then
    mkdir -p "${CONFIG_DIR}"
    info "Created config directory at ${CONFIG_DIR}"
fi

# ── Symlink Installation ───────────────────────────────────────────────────
header "Finishing up…"
read -r -p "Install 'termtube' command to ${BIN_DIR}? [Y/n] " -n 1
echo
if [[ "${REPLY}" =~ ^[Nn]$ ]]; then
    info "Skipping PATH installation."
    echo -e "\n${BOLD}Run TermTube manually:${RESET}  ${GREEN}${APP_DIR}/termtube${RESET}"
else
    mkdir -p "${BIN_DIR}"
    ln -sf "${APP_DIR}/termtube" "${BIN_DIR}/termtube"

    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        warn "${BIN_DIR} is not in your PATH."
        info "Add this to your ~/.bashrc or ~/.zshrc:"
        echo -e "  ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
    else
        success "Symlinked termtube to ${BIN_DIR}/termtube"
        echo -e "\n${BOLD}Setup complete! Run it anywhere with:${RESET} ${GREEN}termtube${RESET}"
    fi
fi

echo ""
info "Config: ${CONFIG_DIR}/config.yaml  (created on first run)"
info "Cookies: place your cookies.txt at ${CONFIG_DIR}/cookies.txt"
