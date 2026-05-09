#!/usr/bin/env bash
# TermTube v2 — Uninstall script.
#
# Removes the application, optionally removes config/cache/history.
# Prompts before destructive operations.

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }

# ── Paths ──────────────────────────────────────────────────────────────────
APP_DIR="$HOME/.local/share/TermTube"
BIN_LINK="$HOME/.local/bin/termtube"
BIN_LINK_ALT="$HOME/bin/termtube"
CONFIG_DIR="$HOME/.config/TermTube"
CACHE_DIR="$HOME/.cache/termtube"

# ── Header ─────────────────────────────────────────────────────────────────
echo -e "${BOLD}TermTube v2 — Uninstaller${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will remove TermTube from your system."
echo ""

# Track what was removed for summary
removed=()
skipped=()

# ── Step 1: Kill running processes ─────────────────────────────────────────
if pgrep -f "termtube" &>/dev/null || pgrep -f "TermTubeApp" &>/dev/null; then
    warn "TermTube appears to be running."
    read -r -p "Kill running TermTube processes? [Y/n] " reply
    if [[ ! "$reply" =~ ^[Nn]$ ]]; then
        pkill -f "termtube" 2>/dev/null || true
        pkill -f "TermTubeApp" 2>/dev/null || true
        sleep 0.5
        success "Killed running processes"
    fi
fi

# ── Step 2: Remove app directory ───────────────────────────────────────────
echo ""
if [[ -e "$APP_DIR" ]]; then
    if [[ -L "$APP_DIR" ]]; then
        local_target="$(readlink "$APP_DIR")"
        info "App directory is a symlink → $local_target"
        info "Only the symlink will be removed (your source code is untouched)."
    fi
    rm -rf "$APP_DIR"
    removed+=("$APP_DIR")
    success "Removed $APP_DIR"
else
    info "App directory not found (already removed): $APP_DIR"
fi

# ── Step 3: Remove CLI symlinks ────────────────────────────────────────────
for link in "$BIN_LINK" "$BIN_LINK_ALT"; do
    if [[ -L "$link" ]] || [[ -f "$link" ]]; then
        rm -f "$link"
        removed+=("$link")
        success "Removed $link"
    fi
done

# ── Step 4: Config directory ───────────────────────────────────────────────
echo ""
if [[ -d "$CONFIG_DIR" ]]; then
    echo -e "Config directory: ${BOLD}$CONFIG_DIR${RESET}"
    echo "  Contains: config.yaml, cookies.txt, history, playlists, hidden list"
    read -r -p "Remove config? ($CONFIG_DIR) [y/N] " reply
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        removed+=("$CONFIG_DIR")
        success "Removed $CONFIG_DIR"
    else
        skipped+=("$CONFIG_DIR")
        info "Kept $CONFIG_DIR"
    fi
fi

# ── Step 5: Cache directory ────────────────────────────────────────────────
if [[ -d "$CACHE_DIR" ]]; then
    # Show cache size
    local_size="$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1)"
    echo ""
    echo -e "Cache directory: ${BOLD}$CACHE_DIR${RESET} (${local_size:-unknown size})"
    echo "  Contains: thumbnails, video metadata cache, SponsorBlock data"
    read -r -p "Remove cache? ($CACHE_DIR) [y/N] " reply
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        rm -rf "$CACHE_DIR"
        removed+=("$CACHE_DIR")
        success "Removed $CACHE_DIR"
    else
        skipped+=("$CACHE_DIR")
        info "Kept $CACHE_DIR"
    fi
fi

# ── Step 6: Watch history and playlists (if config was kept) ───────────────
if [[ -d "$CONFIG_DIR" ]]; then
    local has_data=false
    for f in "$CONFIG_DIR/history.json" "$CONFIG_DIR/playlists.json" "$CONFIG_DIR/search_history.json"; do
        [[ -f "$f" ]] && has_data=true && break
    done
    if [[ "$has_data" == true ]]; then
        echo ""
        read -r -p "Remove watch history and playlists? [y/N] " reply
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            rm -f "$CONFIG_DIR/history.json" "$CONFIG_DIR/playlists.json" \
                  "$CONFIG_DIR/search_history.json" "$CONFIG_DIR/hidden.json" \
                  "$CONFIG_DIR/subscriptions.json"
            removed+=("watch history & playlists")
            success "Removed watch history and playlists"
        else
            skipped+=("watch history & playlists")
            info "Kept watch history and playlists"
        fi
    fi
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Uninstall Summary ━━━${RESET}"
echo ""

if [[ ${#removed[@]} -gt 0 ]]; then
    echo -e "${GREEN}Removed:${RESET}"
    for item in "${removed[@]}"; do
        echo -e "  ${GREEN}✓${RESET} $item"
    done
fi

if [[ ${#skipped[@]} -gt 0 ]]; then
    echo -e "${YELLOW}Kept:${RESET}"
    for item in "${skipped[@]}"; do
        echo -e "  ${YELLOW}•${RESET} $item"
    done
fi

echo ""
echo -e "${GREEN}TermTube has been uninstalled.${RESET}"
