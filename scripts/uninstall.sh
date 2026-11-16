#!/usr/bin/env bash
# TermTube uninstaller — complete removal of all installed components.

set -euo pipefail

readonly APP_DIR="$HOME/.local/share/TermTube"
readonly BIN_LINK="$HOME/.local/bin/termtube"
readonly CONFIG_DIR="$HOME/.config/TermTube"
readonly CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/termtube"
readonly LOG_DIR="${TMPDIR:-/tmp}/TermTube"
readonly DEPS_DIR="$HOME/.local/termtube-deps"

if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BOLD=''; DIM=''; RESET=''
fi

info()    { echo -e "  ${DIM}▸${RESET} $*"; }
success() { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✗${RESET} $*" >&2; }

PURGE=false
FORCE=false

for arg in "$@"; do
    case "$arg" in
        --purge)    PURGE=true ;;
        --force|-f) FORCE=true ;;
        --help|-h)
            cat <<'EOF'

  TermTube Uninstaller
  ════════════════════

    Usage: bash scripts/uninstall.sh [OPTIONS]

  Options:
    (default)      Remove app files and binary symlink.
                   Preserves config (~/.config/TermTube/).

    --purge        Also remove config, cache, and logs.
                   Complete removal of all TermTube traces.

    --force, -f    Skip confirmation prompt.

    --help, -h     Show this help message.

EOF
            exit 0
            ;;
        *) error "Unknown option: $arg"; exit 1 ;;
    esac
done

_box_center() {
    local text="$1" w="$2"
    local len=${#text}
    local pad=$(( (w - len) / 2 ))
    local right=$(( w - len - pad ))
    printf "%${pad}s%s%${right}s" "" "$text" ""
}
_box_width=35

echo ""
echo -e "${BOLD}┌$(printf '─%.0s' $(seq 1 $_box_width))┐${RESET}"
echo -e "${BOLD}│$(_box_center "TermTube Uninstaller" $_box_width)│${RESET}"
echo -e "${BOLD}└$(printf '─%.0s' $(seq 1 $_box_width))┘${RESET}"
echo ""

items_to_remove=()
sizes=()

check_item() {
    local path="$1" label="$2"
    if [[ -e "$path" || -L "$path" ]]; then
        items_to_remove+=("$path")
        local size=""
        if [[ -d "$path" && ! -L "$path" ]]; then
            size="$(du -sh "$path" 2>/dev/null | cut -f1 | xargs)" || size="?"
        fi
        if [[ -L "$path" ]]; then
            local target
            target="$(readlink "$path" 2>/dev/null)" || target="?"
            echo -e "  ${RED}×${RESET} $label"
            echo -e "      ${DIM}$path → $target${RESET}"
        elif [[ -n "$size" ]]; then
            echo -e "  ${RED}×${RESET} $label ${DIM}($size)${RESET}"
            echo -e "      ${DIM}$path${RESET}"
        else
            echo -e "  ${RED}×${RESET} $label"
            echo -e "      ${DIM}$path${RESET}"
        fi
    fi
}

echo -e "  ${BOLD}The following will be removed:${RESET}"
echo ""

check_item "$APP_DIR"  "Application files"
check_item "$BIN_LINK" "CLI symlink"

check_item "$DEPS_DIR"  "Binary dependencies (deno, ffmpeg, mpv)"

if [[ "$PURGE" == true ]]; then
    check_item "$CONFIG_DIR" "Configuration"
    check_item "$CACHE_DIR"  "Cache data"
    check_item "$LOG_DIR"    "Log files"
fi

if [[ ${#items_to_remove[@]} -eq 0 ]]; then
    echo ""
    success "Nothing to remove. TermTube is not installed."
    exit 0
fi

if [[ "$PURGE" != true ]]; then
    echo ""
    echo -e "  ${BOLD}Will be preserved:${RESET}"
    if [[ -d "$CONFIG_DIR" ]]; then
        echo -e "  ${GREEN}✓${RESET} Config ${DIM}($CONFIG_DIR)${RESET}"
    fi
    if [[ -d "$CACHE_DIR" ]]; then
        echo -e "  ${GREEN}✓${RESET} Cache ${DIM}($CACHE_DIR)${RESET}"
    fi
    echo -e "      ${DIM}Use --purge to remove everything.${RESET}"
fi

if [[ "$FORCE" != true ]]; then
    echo ""
    read -r -p "  Proceed with uninstall? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo ""
        info "Uninstall cancelled."
        exit 0
    fi
fi

# Only processes started from the installed app dir (its venv python and sources), never other "termtube" matches.
if pgrep -f "$APP_DIR/" &>/dev/null 2>&1; then
    warn "TermTube process detected. Stopping…"
    pkill -f "$APP_DIR/" 2>/dev/null || true
    sleep 0.5
fi

# mpv IPC sockets: same directory as src/plat.py _unix_ipc_dir()
ipc_dir="${XDG_RUNTIME_DIR:-/tmp/termtube-$(id -u)}"
rm -f "$ipc_dir"/termtube-mpv*.sock
rmdir "/tmp/termtube-$(id -u)" 2>/dev/null || true

echo ""
echo -e "  ${BOLD}Removing…${RESET}"

remove_item() {
    local path="$1" label="$2"
    if [[ -L "$path" ]]; then
        rm -f "$path" && success "Removed symlink: $label" || warn "Could not remove: $path"
    elif [[ -d "$path" ]]; then
        rm -rf "$path" && success "Removed: $label" || warn "Could not remove: $path"
    elif [[ -f "$path" ]]; then
        rm -f "$path" && success "Removed: $label" || warn "Could not remove: $path"
    fi
}

remove_item "$BIN_LINK" "CLI symlink"
remove_item "$APP_DIR"  "Application files"
remove_item "$DEPS_DIR" "Binary dependencies"

if [[ "$PURGE" == true ]]; then
    remove_item "$CONFIG_DIR" "Configuration"
    remove_item "$CACHE_DIR"  "Cache data"
    remove_item "$LOG_DIR"    "Log files"
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  TermTube uninstalled successfully.${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

if [[ "$PURGE" != true && -d "$CONFIG_DIR" ]]; then
    echo ""
    echo -e "  ${DIM}Config preserved at: $CONFIG_DIR${RESET}"
    echo -e "  ${DIM}Run with --purge to remove all traces.${RESET}"
fi
echo ""
exit 0
