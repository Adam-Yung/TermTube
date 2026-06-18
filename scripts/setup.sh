#!/usr/bin/env bash
# TermTube installer — minimal setup that bootstraps dependencies from GitHub.
#
# Requirements: git, python3.11+, curl
# All other dependencies (yt-dlp, deno, ffmpeg, mpv) are downloaded
# automatically into ~/.local/termtube-deps/bin/ by src/bootstrap.py.

set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────────────────
readonly VERSION="0.2.0"
readonly APP_NAME="TermTube"
readonly APP_DIR="$HOME/.local/share/TermTube"
readonly BIN_DIR="$HOME/.local/bin"
readonly CONFIG_DIR="$HOME/.config/TermTube"
readonly PYTHON_MIN="3.11"

# ── Colours & Output ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BLUE='\033[0;34m'; BOLD='\033[1m'
    DIM='\033[2m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BLUE=''; BOLD=''; DIM=''; RESET=''
fi

info()    { echo -e "${CYAN}▸${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }
step()    { echo -e "${BLUE}→${RESET} $*"; }

# ── Help ──────────────────────────────────────────────────────────────────────
show_help() {
    cat <<'EOF'

  TermTube Setup Script
  ═════════════════════

  Usage: bash setup.sh [OPTIONS]

  Install Modes:
    (default)     Copy project to ~/.local/share/TermTube.
                  Standard end-user installation. Source changes require re-run.

    --sync        Symlink installation → current directory.
                  For development: edits are immediately live.

  Options:
    --no-deps     Skip dependency bootstrap (only set up Python venv).
    --no-prompt   Non-interactive mode (accept all defaults).
    --help, -h    Show this help message and exit.

  Prerequisites:
    git           Version control (already have it if you cloned this)
    python3.11+   Python interpreter
    curl          For downloading dependencies (used by bootstrap.py)

  What gets installed:
    ~/.local/share/TermTube/     App files + Python venv
    ~/.local/termtube-deps/bin/  Binary deps (yt-dlp, deno, ffmpeg, mpv)
    ~/.local/bin/termtube        CLI symlink
    ~/.config/TermTube/          Config (created on first run)

EOF
    exit 0
}

# ── Argument Parsing ──────────────────────────────────────────────────────────
SYNC_MODE=false
SKIP_DEPS=false
INTERACTIVE=true

for arg in "$@"; do
    case "$arg" in
        --sync)      SYNC_MODE=true ;;
        --no-deps)   SKIP_DEPS=true ;;
        --no-prompt) INTERACTIVE=false ;;
        --help|-h)   show_help ;;
        *)           error "Unknown option: $arg"; echo "  Run 'bash setup.sh --help' for usage."; exit 1 ;;
    esac
done

ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Prerequisite Checks ───────────────────────────────────────────────────────
check_prerequisites() {
    local missing=()

    if ! command -v git &>/dev/null; then
        missing+=("git")
    fi

    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing prerequisites: ${missing[*]}"
        echo "  These must be installed before running setup."
        exit 1
    fi

    success "Prerequisites OK (git, curl)"
}

# ── Python Detection ──────────────────────────────────────────────────────────
check_python_version() {
    local py="$1"
    "$py" -c "
import sys
v = sys.version_info
if (v.major, v.minor) >= (3, 11):
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null
}

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" &>/dev/null && check_python_version "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# ── Venv Setup ────────────────────────────────────────────────────────────────
setup_venv() {
    local venv_dir="$1"
    local requirements="$2"

    local py
    if ! py=$(find_python); then
        error "Python >= $PYTHON_MIN not found."
        echo ""
        echo "  Install Python >= $PYTHON_MIN from https://python.org"
        return 1
    fi

    local ver
    ver=$("$py" --version 2>&1)
    info "Using $ver ($py)"

    if [[ -d "$venv_dir" ]]; then
        local venv_pip="$venv_dir/bin/pip"
        if [[ -f "$venv_pip" ]] && "$venv_pip" --version &>/dev/null; then
            info "Virtual environment exists — upgrading dependencies…"
        else
            warn "Existing venv is stale (interpreter changed). Recreating…"
            rm -rf "$venv_dir"
            "$py" -m venv "$venv_dir"
        fi
    else
        step "Creating virtual environment…"
        "$py" -m venv "$venv_dir"
    fi

    # Hash-based cache: skip pip install when requirements.txt is unchanged
    local hash_file="$venv_dir/.requirements.sha256"
    local current_hash=""
    if [[ -f "$requirements" ]]; then
        if command -v sha256sum &>/dev/null; then
            current_hash=$(sha256sum "$requirements" | awk '{print $1}')
        elif command -v shasum &>/dev/null; then
            current_hash=$(shasum -a 256 "$requirements" | awk '{print $1}')
        fi
    fi
    local cached_hash=""
    [[ -f "$hash_file" ]] && cached_hash=$(<"$hash_file")

    if [[ -n "$current_hash" && "$cached_hash" == "$current_hash" ]]; then
        info "Requirements unchanged — skipping pip install."
        success "Python environment ready."
        return
    fi

    step "Installing Python packages…"
    "$venv_dir/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
    "$venv_dir/bin/pip" install --quiet -r "$requirements"
    [[ -n "$current_hash" ]] && printf '%s' "$current_hash" > "$hash_file"
    success "Python environment ready."
}

# ── Sync Mode Prompt ──────────────────────────────────────────────────────────
prompt_sync_mode() {
    if [[ "$INTERACTIVE" != true ]]; then
        return
    fi

    if [[ "$SYNC_MODE" == true ]]; then
        return
    fi

    echo ""
    echo -e "  ${BOLD}Choose installation mode:${RESET}"
    echo ""
    echo -e "    ${GREEN}1${RESET}) ${BOLD}Standard${RESET} (recommended)"
    echo -e "       Copies files to ~/.local/share/TermTube"
    echo -e "       ${DIM}Stable, isolated from source changes${RESET}"
    echo ""
    echo -e "    ${GREEN}2${RESET}) ${BOLD}Developer sync${RESET}"
    echo -e "       Symlinks to current directory"
    echo -e "       ${DIM}Edits take effect immediately${RESET}"
    echo ""
    read -r -p "  Select [1/2]: " choice
    case "$choice" in
        2) SYNC_MODE=true ;;
        *) SYNC_MODE=false ;;
    esac
}

# ── File Installation ─────────────────────────────────────────────────────────
install_files() {
    if [[ "${ORIG_DIR}" == "${APP_DIR}" ]]; then
        info "Already running from install directory."
        return 0
    fi

    if [[ "$SYNC_MODE" == true ]]; then
        header "Developer Sync Mode"
        rm -rf "${APP_DIR}"
        mkdir -p "$(dirname "${APP_DIR}")"
        ln -s "${ORIG_DIR}" "${APP_DIR}"
        success "Symlinked ${APP_DIR} → ${ORIG_DIR}"
        info "Edits in source are immediately live."
    else
        header "Standard Installation"
        rm -rf "${APP_DIR}"
        mkdir -p "${APP_DIR}"

        if [[ -d "${ORIG_DIR}/src" ]]; then
            cp -a "${ORIG_DIR}/src" "${APP_DIR}/"
        fi

        if [[ -d "${ORIG_DIR}/scripts" ]]; then
            cp -a "${ORIG_DIR}/scripts" "${APP_DIR}/"
        fi

        for f in requirements.txt termtube termtube.cmd; do
            if [[ -f "${ORIG_DIR}/$f" ]]; then
                cp -a "${ORIG_DIR}/$f" "${APP_DIR}/"
            fi
        done

        chmod +x "${APP_DIR}/termtube" "${APP_DIR}/setup.sh" "${APP_DIR}/uninstall.sh" 2>/dev/null || true
        success "Project files installed to ${APP_DIR}"
    fi
}

# ── PATH Symlink ──────────────────────────────────────────────────────────────
install_binary() {
    local do_install=true

    if [[ "$INTERACTIVE" == true ]]; then
        echo ""
        read -r -p "  Install 'termtube' command to ${BIN_DIR}? [Y/n] " reply
        if [[ "${reply}" =~ ^[Nn]$ ]]; then
            do_install=false
        fi
    fi

    if [[ "$do_install" == true ]]; then
        mkdir -p "${BIN_DIR}"
        ln -sf "${APP_DIR}/termtube" "${BIN_DIR}/termtube"

        if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
            warn "${BIN_DIR} is not in your PATH."
            echo ""
            echo "  Add to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
            echo -e "    ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
            echo ""
        else
            success "Installed: ${BIN_DIR}/termtube"
        fi
    else
        info "Skipped PATH installation."
        echo -e "  Run manually: ${GREEN}${APP_DIR}/termtube${RESET}"
    fi
}

# ── Bootstrap Dependencies ────────────────────────────────────────────────────
bootstrap_deps() {
    header "Binary Dependencies"
    info "Downloading yt-dlp, deno, ffmpeg, mpv from GitHub releases..."
    info "Install path: ~/.local/termtube-deps/bin/"
    echo ""

    local venv_python="${APP_DIR}/.venv/bin/python"
    if [[ ! -f "$venv_python" ]]; then
        error "Python venv not found at ${APP_DIR}/.venv"
        return 1
    fi

    "$venv_python" -m src.bootstrap
    local rc=$?

    if [[ $rc -eq 0 ]]; then
        success "All dependencies installed."
    else
        warn "Some dependencies failed to install."
        echo "  You can retry later with: termtube --update"
    fi
    return $rc
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    local title="TermTube Installer"
    local subtitle="v${VERSION}"
    local width=37
    local inner=$((width - 2))

    _center() {
        local text="$1" w="$2"
        local len=${#text}
        local pad=$(( (w - len) / 2 ))
        local right=$(( w - len - pad ))
        printf "%${pad}s%s%${right}s" "" "$text" ""
    }

    echo ""
    echo -e "${BOLD}┌$(printf '─%.0s' $(seq 1 $inner))┐${RESET}"
    echo -e "${BOLD}│$(_center "$title" $inner)│${RESET}"
    echo -e "${BOLD}│$(_center "$subtitle" $inner)│${RESET}"
    echo -e "${BOLD}└$(printf '─%.0s' $(seq 1 $inner))┘${RESET}"

    # Check prerequisites
    header "Prerequisites"
    check_prerequisites

    # Prompt for install mode
    prompt_sync_mode

    # Install project files
    install_files

    # Python environment
    local venv_dir="${APP_DIR}/.venv"
    local requirements="${APP_DIR}/requirements.txt"

    header "Python Environment"
    setup_venv "$venv_dir" "$requirements" || exit 1

    # Bootstrap binary dependencies
    if [[ "$SKIP_DEPS" != true ]]; then
        bootstrap_deps || true
    fi

    # Config directory
    if [[ ! -d "${CONFIG_DIR}" ]]; then
        mkdir -p "${CONFIG_DIR}"
        info "Created config directory: ${CONFIG_DIR}"
    fi

    # Install binary to PATH
    header "Finishing Up"
    install_binary

    # Summary
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}${BOLD}  Setup complete!${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo -e "  ${BOLD}Run:${RESET}     ${GREEN}termtube${RESET}"
    echo -e "  ${BOLD}Config:${RESET}  ${CONFIG_DIR}/config.yaml"
    echo -e "  ${BOLD}Cookies:${RESET} ${CONFIG_DIR}/cookies.txt"
    echo ""
    if [[ "$SYNC_MODE" == true ]]; then
        echo -e "  ${DIM}Mode: developer sync (symlinked)${RESET}"
    else
        echo -e "  ${DIM}Mode: standard install (copied)${RESET}"
    fi
    echo ""
}

main "$@"
