#!/usr/bin/env bash
# TermTube installer — sets up a Python venv and bootstraps binary dependencies
# from GitHub releases.
#
# Prerequisites: python3.11+, curl
# deno, ffmpeg and mpv are downloaded automatically into ~/.local/termtube-deps/bin/
# by src/bootstrap.py; yt-dlp comes from pip (requirements.txt).

set -euo pipefail

# A missing VERSION file only blanks the banner's version; it must not stop the install.
VERSION="$(cat "$(dirname "$0")/../VERSION")" || true
readonly VERSION
readonly APP_DIR="$HOME/.local/share/TermTube"
readonly BIN_DIR="$HOME/.local/bin"
readonly CONFIG_DIR="$HOME/.config/TermTube"
readonly PYTHON_MIN="3.11"

if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BLUE='\033[0;34m'; BOLD='\033[1m'
    RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BLUE=''; BOLD=''; RESET=''
fi

info()    { echo -e "${CYAN}▸${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }
step()    { echo -e "${BLUE}→${RESET} $*"; }

show_help() {
    cat <<'EOF'

  TermTube Setup Script
  ═════════════════════

  Usage: bash scripts/setup.sh [OPTIONS]

  Options:
    --refresh     Replace only the installed code (src, scripts, assets, launcher) from this
                  checkout. Keeps the venv, makes no network calls, installs no packages.
    --no-deps     Skip dependency bootstrap (only set up Python venv).
    --no-prompt   Non-interactive mode (accept all defaults).
    --help, -h    Show this help message and exit.

  Prerequisites:
    python3.11+   Python interpreter
    curl          For downloading dependencies (used by bootstrap.py)

  What gets installed:
    ~/.local/share/TermTube/     App files + Python venv
    ~/.local/termtube-deps/bin/  Binary deps (deno, ffmpeg, mpv)
    ~/.local/bin/termtube        CLI symlink
    ~/.config/TermTube/          Config (created on first run)

EOF
    exit 0
}

SKIP_DEPS=false
INTERACTIVE=true
REFRESH=false

for arg in "$@"; do
    case "$arg" in
        --refresh)   REFRESH=true ;;
        --no-deps)   SKIP_DEPS=true ;;
        --no-prompt) INTERACTIVE=false ;;
        --help|-h)   show_help ;;
        *)           error "Unknown option: $arg"; echo "  Run 'bash scripts/setup.sh --help' for usage."; exit 1 ;;
    esac
done

# Resolve repo root (one level above the scripts/ directory)
ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/setup-shortcut.sh
source "${ORIG_DIR}/scripts/setup-shortcut.sh"

check_prerequisites() {
    local missing=()

    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing prerequisites: ${missing[*]}"
        echo "  These must be installed before running setup."
        exit 1
    fi

    success "Prerequisites OK (curl)"
}

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
    [[ -f "$requirements" ]] && current_hash="$(file_hash "$requirements")"
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

file_hash() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

refresh_files() {
    header "Refreshing the installed copy"
    if [[ ! -d "${APP_DIR}/.venv" ]]; then
        error "No installed app at ${APP_DIR}. Run bash scripts/setup.sh (without --refresh) first."
        exit 1
    fi
    if [[ "${ORIG_DIR}" == "${APP_DIR}" ]]; then
        info "Already running from the install directory."
        return 0
    fi
    local d f
    for d in src scripts assets; do
        [[ -d "${ORIG_DIR}/$d" ]] || continue
        rm -rf "${APP_DIR:?}/$d"
        cp -a "${ORIG_DIR}/$d" "${APP_DIR}/"
    done
    find "${APP_DIR}/src" "${APP_DIR}/scripts" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
    for f in requirements.txt termtube termtube.cmd; do
        [[ -f "${ORIG_DIR}/$f" ]] && cp -a "${ORIG_DIR}/$f" "${APP_DIR}/"
    done
    chmod +x "${APP_DIR}/termtube" 2>/dev/null || true
    chmod +x "${APP_DIR}"/scripts/*.sh 2>/dev/null || true
    write_version
    success "Code replaced in ${APP_DIR}; the venv was not touched."

    local wanted cached=""
    wanted="$(file_hash "${APP_DIR}/requirements.txt")"
    [[ -f "${APP_DIR}/.venv/.requirements.sha256" ]] && cached="$(<"${APP_DIR}/.venv/.requirements.sha256")"
    if [[ -n "$wanted" && "$wanted" != "$cached" ]]; then
        warn "requirements.txt changed since the venv was built: its packages may be out of date."
        echo "  Run bash scripts/setup.sh to rebuild the venv (this downloads packages)."
    fi
}

install_files() {
    if [[ "${ORIG_DIR}" == "${APP_DIR}" ]]; then
        info "Already running from install directory."
        return 0
    fi

    header "Standard Installation"
    rm -rf "${APP_DIR}"
    mkdir -p "${APP_DIR}"

    if [[ -d "${ORIG_DIR}/src" ]]; then
        cp -a "${ORIG_DIR}/src" "${APP_DIR}/"
    fi

    if [[ -d "${ORIG_DIR}/scripts" ]]; then
        cp -a "${ORIG_DIR}/scripts" "${APP_DIR}/"
    fi

    if [[ -d "${ORIG_DIR}/assets" ]]; then
        cp -a "${ORIG_DIR}/assets" "${APP_DIR}/"
    fi

    for f in requirements.txt termtube termtube.cmd VERSION; do
        if [[ -f "${ORIG_DIR}/$f" ]]; then
            cp -a "${ORIG_DIR}/$f" "${APP_DIR}/"
        fi
    done

    chmod +x "${APP_DIR}/termtube" 2>/dev/null || true
    chmod +x "${APP_DIR}"/scripts/*.sh 2>/dev/null || true
    success "Project files installed to ${APP_DIR}"
}

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

bootstrap_deps() {
    header "Binary Dependencies"
    info "Downloading deno, ffmpeg, mpv from GitHub releases..."
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

write_version() {
    local version_file="${APP_DIR}/VERSION"
    local tag=""
    if command -v git &>/dev/null && [[ -d "${ORIG_DIR}/.git" ]]; then
        tag=$(git -C "${ORIG_DIR}" describe --tags --exact-match 2>/dev/null || echo "dev")
    else
        tag="dev"
    fi
    printf '%s' "$tag" > "$version_file"
    info "Version: $tag"
}

main() {
    local title="TermTube Installer"
    local subtitle="${VERSION}"
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

    if [[ "$REFRESH" == true ]]; then
        refresh_files
        return 0
    fi

    # Check prerequisites
    header "Prerequisites"
    check_prerequisites

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

    # Write version file
    write_version

    # Desktop shortcut (prompted)
    install_shortcut

    # Summary
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}${BOLD}  Setup complete!${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo -e "  ${BOLD}Run:${RESET}     ${GREEN}termtube${RESET}"
    echo -e "  ${BOLD}Config:${RESET}  ${CONFIG_DIR}/config.yaml"

    echo ""
}

main "$@"
