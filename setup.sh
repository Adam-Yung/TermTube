#!/usr/bin/env bash
# TermTube setup — creates a Python environment and installs dependencies.
#
# Strategy (tries in order):
#   1. mamba  — fastest conda-compatible solver
#   2. conda  — standard Anaconda/Miniconda/Miniforge
#   3. python3 venv — universal fallback (no conda required)

set -euo pipefail

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
    # Strip comment lines and the system-tool section before passing to pip
    grep -v '^\s*#' "${REQUIREMENTS}" | grep -v '^\s*$' | \
        "$pip_bin" install --quiet -r /dev/stdin
    success "Dependencies installed."
}

check_python_version() {
    local py="$1"
    local ver
    ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    # Compare: major.minor >= 3.11
    python3 -c "import sys; sys.exit(0 if tuple(map(int,'$ver'.split('.'))) >= (3,11) else 1)" 2>/dev/null
}

# ── 1. Try mamba ───────────────────────────────────────────────────────────

try_mamba() {
    command -v mamba &>/dev/null || return 1
    header "Setting up with mamba (conda environment '${ENV_NAME}')"

    if mamba env list 2>/dev/null | grep -q "^${ENV_NAME} "; then
        info "Environment '${ENV_NAME}' already exists — updating…"
        mamba run -n "${ENV_NAME}" pip install --quiet -r "${REQUIREMENTS}"
    else
        info "Creating conda environment '${ENV_NAME}' with Python ${PYTHON_MIN}…"
        mamba create -y -n "${ENV_NAME}" "python>=${PYTHON_MIN}" pip --quiet
        mamba run -n "${ENV_NAME}" pip install --quiet -r "${REQUIREMENTS}"
    fi

    success "mamba environment '${ENV_NAME}' is ready."
    return 0
}

# ── 2. Try conda ───────────────────────────────────────────────────────────

try_conda() {
    command -v conda &>/dev/null || return 1
    header "Setting up with conda (environment '${ENV_NAME}')"

    if conda env list 2>/dev/null | grep -q "^${ENV_NAME} "; then
        info "Environment '${ENV_NAME}' already exists — updating…"
        conda run -n "${ENV_NAME}" pip install --quiet -r "${REQUIREMENTS}"
    else
        info "Creating conda environment '${ENV_NAME}' with Python ${PYTHON_MIN}…"
        conda create -y -n "${ENV_NAME}" "python>=${PYTHON_MIN}" pip --quiet
        conda run -n "${ENV_NAME}" pip install --quiet -r "${REQUIREMENTS}"
    fi

    success "conda environment '${ENV_NAME}' is ready."
    return 0
}

# ── 3. Fall back to python venv ────────────────────────────────────────────

try_venv() {
    header "Setting up with Python venv (.venv/)"

    # Find a Python >= 3.11
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

# 1. Persistence / Copy
if [[ "${ORIG_DIR}" != "${APP_DIR}" ]]; then
    header "Copying files for persistent installation…"
    mkdir -p "${APP_DIR}"
    
    # Remove existing src just in case this is an update
    rm -rf "${APP_DIR}/src"
    
    # Copy essential components safely
    if [[ -d "${ORIG_DIR}/src" ]]; then
        cp -a "${ORIG_DIR}/src" "${APP_DIR}/"
    fi
    
    # Add uninstall.sh to the list of files to copy
    for f in requirements.txt termtube setup.sh uninstall.sh theme.tcss; do
        if [[ -f "${ORIG_DIR}/$f" ]]; then
            cp -a "${ORIG_DIR}/$f" "${APP_DIR}/"
        fi
    done
    
    # Make sure to chmod the new script too
    chmod +x "${APP_DIR}/termtube" "${APP_DIR}/setup.sh" "${APP_DIR}/uninstall.sh"
    success "Copied project files to ${APP_DIR}"
fi

# Switch context to the new persistent directory
SCRIPT_DIR="${APP_DIR}"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
ENV_NAME="termtube"
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

# Set up Python environment
header "Setting up Python environment…"
try_mamba || try_conda || try_venv || {
    error "Could not create a Python environment."
    error "Install mamba, conda, or Python >= 3.11 and try again."
    exit 1
}

# ── Symlink Installation ───────────────────────────────────────────────────
header "Finishing up…"
read -p "Install 'termtube' command to ${BIN_DIR}? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    info "Skipping PATH installation."
    echo -e "\n${BOLD}Run TermTube manually:${RESET}  ${GREEN}${APP_DIR}/termtube${RESET}"
else
    mkdir -p "${BIN_DIR}"
    ln -sf "${APP_DIR}/termtube" "${BIN_DIR}/termtube"
    
    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        warn "${BIN_DIR} is not in your PATH."
        info "To use the 'termtube' command globally, add this to your ~/.bashrc or ~/.zshrc:"
        echo -e "  ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
    else
        success "Symlinked termtube to ${BIN_DIR}/termtube"
        echo -e "\n${BOLD}Setup complete! Run it anywhere with:${RESET} ${GREEN}termtube${RESET}"
    fi
fi
