#!/usr/bin/env bash
# TermTube uninstaller — complete removal of all installed components.

set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────────────────
readonly APP_DIR="$HOME/.local/share/TermTube"
readonly BIN_LINK="$HOME/.local/bin/termtube"
readonly CONFIG_DIR="$HOME/.config/TermTube"
readonly CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/TermTube"
readonly LOG_DIR="${TMPDIR:-/tmp}/TermTube"

# ── Colours & Output ──────────────────────────────────────────────────────────
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

# ── Argument Parsing ──────────────────────────────────────────────────────────
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

  Usage: bash uninstall.sh [OPTIONS]

  Options:
    (default)      Remove app files and binary symlink.
                   Preserves config and cookies (~/.config/TermTube/).

    --purge        Also remove config, cookies, cache, and logs.
                   Complete removal of all TermTube traces.

    --force, -f    Skip confirmation prompt.

    --help, -h     Show this help message.

EOF
            exit 0
            ;;
        *) error "Unknown option: $arg"; exit 1 ;;
    esac
done

# ── Discovery ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}┌─────────────────────────────────────┐${RESET}"
echo -e "${BOLD}│       TermTube Uninstaller           │${RESET}"
echo -e "${BOLD}└─────────────────────────────────────┘${RESET}"
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

if [[ "$PURGE" == true ]]; then
    check_item "$CONFIG_DIR" "Configuration & cookies"
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
        echo -e "  ${GREEN}✓${RESET} Config & cookies ${DIM}($CONFIG_DIR)${RESET}"
    fi
    if [[ -d "$CACHE_DIR" ]]; then
        echo -e "  ${GREEN}✓${RESET} Cache ${DIM}($CACHE_DIR)${RESET}"
    fi
    echo -e "      ${DIM}Use --purge to remove everything.${RESET}"
fi

# ── Confirmation ──────────────────────────────────────────────────────────────
if [[ "$FORCE" != true ]]; then
    echo ""
    read -r -p "  Proceed with uninstall? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo ""
        info "Uninstall cancelled."
        exit 0
    fi
fi

# ── Kill running processes ────────────────────────────────────────────────────
if pgrep -f "termtube" &>/dev/null 2>&1; then
    warn "TermTube process detected. Stopping…"
    pkill -f "termtube" 2>/dev/null || true
    sleep 0.5
fi

# Clean up mpv IPC socket if present
if [[ -S "/tmp/termtube-mpv.sock" ]]; then
    rm -f "/tmp/termtube-mpv.sock"
fi

# ── Removal ───────────────────────────────────────────────────────────────────
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

if [[ "$PURGE" == true ]]; then
    remove_item "$CONFIG_DIR" "Configuration & cookies"
    remove_item "$CACHE_DIR"  "Cache data"
    remove_item "$LOG_DIR"    "Log files"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
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
