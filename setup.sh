#!/usr/bin/env bash
# TermTube installer — cross-platform setup with dependency management.

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
    --deps        Auto-install system dependencies (yt-dlp, mpv, chafa, ffmpeg)
                  using your system's package manager.
    --no-deps     Skip dependency checks entirely.
    --no-prompt   Non-interactive mode (accept all defaults).
    --help, -h    Show this help message and exit.

  Paths:
    Install dir:  ~/.local/share/TermTube
    Config:       ~/.config/TermTube/config.yaml  (created on first run)
    Cookies:      ~/.config/TermTube/cookies.txt  (add manually)
    Binary:       ~/.local/bin/termtube

EOF
    exit 0
}

# ── Argument Parsing ──────────────────────────────────────────────────────────
SYNC_MODE=false
AUTO_DEPS=false
SKIP_DEPS=false
INTERACTIVE=true

for arg in "$@"; do
    case "$arg" in
        --sync)      SYNC_MODE=true ;;
        --deps)      AUTO_DEPS=true ;;
        --no-deps)   SKIP_DEPS=true ;;
        --no-prompt) INTERACTIVE=false ;;
        --help|-h)   show_help ;;
        *)           error "Unknown option: $arg"; echo "  Run 'bash setup.sh --help' for usage."; exit 1 ;;
    esac
done

ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── OS Detection ──────────────────────────────────────────────────────────────
detect_os() {
    local uname_s
    uname_s="$(uname -s)"
    case "$uname_s" in
        Darwin)  OS="macos" ;;
        Linux)   OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)       OS="unknown" ;;
    esac
}

detect_package_manager() {
    if [[ "$OS" == "macos" ]]; then
        if command -v brew &>/dev/null; then
            PKG_MGR="brew"
        else
            PKG_MGR="none"
        fi
    elif [[ "$OS" == "linux" ]]; then
        if command -v apt-get &>/dev/null; then
            PKG_MGR="apt"
        elif command -v dnf &>/dev/null; then
            PKG_MGR="dnf"
        elif command -v pacman &>/dev/null; then
            PKG_MGR="pacman"
        elif command -v zypper &>/dev/null; then
            PKG_MGR="zypper"
        elif command -v apk &>/dev/null; then
            PKG_MGR="apk"
        else
            PKG_MGR="none"
        fi
    else
        PKG_MGR="none"
    fi
}

# ── Dependency Installation ───────────────────────────────────────────────────
pkg_install() {
    local pkg="$1"
    case "$PKG_MGR" in
        brew)    brew install "$pkg" ;;
        apt)     sudo apt-get install -y "$pkg" ;;
        dnf)     sudo dnf install -y "$pkg" ;;
        pacman)  sudo pacman -S --noconfirm "$pkg" ;;
        zypper)  sudo zypper install -y "$pkg" ;;
        apk)     sudo apk add "$pkg" ;;
        *)       return 1 ;;
    esac
}

pkg_name() {
    local tool="$1"
    case "$PKG_MGR" in
        apt)
            case "$tool" in
                yt-dlp)  echo "yt-dlp" ;;
                mpv)     echo "mpv" ;;
                chafa)   echo "chafa" ;;
                ffmpeg)  echo "ffmpeg" ;;
                *)       echo "$tool" ;;
            esac ;;
        pacman)
            case "$tool" in
                yt-dlp)  echo "yt-dlp" ;;
                *)       echo "$tool" ;;
            esac ;;
        *)  echo "$tool" ;;
    esac
}

install_hint() {
    local tool="$1"
    case "$PKG_MGR" in
        brew)    echo "brew install $tool" ;;
        apt)     echo "sudo apt install $(pkg_name "$tool")" ;;
        dnf)     echo "sudo dnf install $(pkg_name "$tool")" ;;
        pacman)  echo "sudo pacman -S $(pkg_name "$tool")" ;;
        zypper)  echo "sudo zypper install $(pkg_name "$tool")" ;;
        apk)     echo "sudo apk add $(pkg_name "$tool")" ;;
        none)    echo "Install '$tool' using your system's package manager" ;;
    esac
}

check_and_install_deps() {
    local -a required=(yt-dlp mpv)
    local -a optional=(chafa ffmpeg)
    local missing_required=()
    local missing_optional=()

    for tool in "${required[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing_required+=("$tool")
        else
            success "$tool found ($(command -v "$tool"))"
        fi
    done

    for tool in "${optional[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing_optional+=("$tool")
        else
            success "$tool found"
        fi
    done

    if [[ ${#missing_required[@]} -eq 0 && ${#missing_optional[@]} -eq 0 ]]; then
        success "All dependencies satisfied."
        return 0
    fi

    if [[ ${#missing_required[@]} -gt 0 ]]; then
        warn "Missing required: ${missing_required[*]}"
    fi
    if [[ ${#missing_optional[@]} -gt 0 ]]; then
        info "Missing optional: ${missing_optional[*]}"
    fi

    if [[ "$PKG_MGR" == "none" ]]; then
        error "No supported package manager detected."
        echo ""
        for tool in "${missing_required[@]}"; do
            echo "  Required: $tool"
        done
        for tool in "${missing_optional[@]}"; do
            echo "  Optional: $tool"
        done
        if [[ ${#missing_required[@]} -gt 0 ]]; then
            echo ""
            error "Install required dependencies manually, then re-run setup."
            return 1
        fi
        return 0
    fi

    local should_install=false
    if [[ "$AUTO_DEPS" == true ]]; then
        should_install=true
    elif [[ "$INTERACTIVE" == true ]]; then
        echo ""
        echo -e "  Install missing dependencies using ${BOLD}${PKG_MGR}${RESET}?"
        if [[ ${#missing_required[@]} -gt 0 ]]; then
            echo -e "    Required: ${BOLD}${missing_required[*]}${RESET}"
        fi
        if [[ ${#missing_optional[@]} -gt 0 ]]; then
            echo -e "    Optional: ${DIM}${missing_optional[*]}${RESET}"
        fi
        echo ""
        read -r -p "  Install now? [Y/n] " reply
        if [[ ! "${reply}" =~ ^[Nn]$ ]]; then
            should_install=true
        fi
    fi

    if [[ "$should_install" == true ]]; then
        for tool in "${missing_required[@]}" "${missing_optional[@]}"; do
            step "Installing $(pkg_name "$tool") via $PKG_MGR…"
            if pkg_install "$(pkg_name "$tool")"; then
                success "$tool installed."
            else
                if [[ " ${missing_required[*]} " == *" $tool "* ]]; then
                    error "Failed to install $tool."
                    error "Try manually: $(install_hint "$tool")"
                    return 1
                else
                    warn "Could not install $tool (optional). $(install_hint "$tool")"
                fi
            fi
        done
    else
        if [[ ${#missing_required[@]} -gt 0 ]]; then
            echo ""
            warn "Required dependencies not installed. You'll need them to run TermTube:"
            for tool in "${missing_required[@]}"; do
                echo "    $(install_hint "$tool")"
            done
        fi
    fi
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
        case "$PKG_MGR" in
            brew)    echo "  Install: brew install python@3.12" ;;
            apt)     echo "  Install: sudo apt install python3.12 python3.12-venv" ;;
            dnf)     echo "  Install: sudo dnf install python3.12" ;;
            pacman)  echo "  Install: sudo pacman -S python" ;;
            *)       echo "  Install Python >= $PYTHON_MIN from https://python.org" ;;
        esac
        return 1
    fi

    local ver
    ver=$("$py" --version 2>&1)
    info "Using $ver ($py)"

    if [[ -d "$venv_dir" ]]; then
        # Check if the venv's Python is still valid
        local venv_py="$venv_dir/bin/python3"
        if [[ -f "$venv_py" ]] && "$venv_py" --version &>/dev/null; then
            info "Virtual environment exists — upgrading dependencies…"
        else
            warn "Existing venv is stale (Python interpreter changed). Recreating…"
            rm -rf "$venv_dir"
            "$py" -m venv "$venv_dir"
        fi
    else
        step "Creating virtual environment…"
        "$py" -m venv "$venv_dir"
    fi

    step "Installing Python packages…"
    "$venv_dir/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
    "$venv_dir/bin/pip" install --quiet -r "$requirements"
    success "Python environment ready."
}

# ── Sync Mode Prompt ──────────────────────────────────────────────────────────
prompt_sync_mode() {
    if [[ "$INTERACTIVE" != true ]]; then
        return
    fi

    # If --sync was explicitly passed, don't prompt
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

        for f in requirements.txt termtube setup.sh uninstall.sh; do
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

    detect_os
    detect_package_manager
    info "Detected: ${OS} / package manager: ${PKG_MGR:-none}"

    # Prompt for install mode
    prompt_sync_mode

    # System dependencies
    if [[ "$SKIP_DEPS" != true ]]; then
        header "System Dependencies"
        check_and_install_deps || exit 1
    fi

    # Install project files
    install_files

    # Python environment
    local venv_dir="${APP_DIR}/.venv"
    local requirements="${APP_DIR}/requirements.txt"

    header "Python Environment"
    setup_venv "$venv_dir" "$requirements" || exit 1

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
