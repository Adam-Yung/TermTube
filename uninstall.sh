#!/usr/bin/env bash
# TermTube uninstaller.

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'

echo -e "${BOLD}TermTube Uninstaller${RESET}"
echo "This will permanently remove:"
echo "  - $HOME/.local/share/TermTube"
echo "  - $HOME/.local/bin/termtube"
echo ""
echo -e "${YELLOW}⚠${RESET}  Config and cookies at ~/.config/TermTube/ are left untouched."
echo "   Remove manually if you no longer need them."
echo ""
read -r -p "Are you sure you want to proceed? [y/N] " -n 1
echo
if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
    echo "Uninstall canceled."
    exit 0
fi

rm -f "$HOME/.local/bin/termtube"
rm -rf "$HOME/.local/share/TermTube"

echo -e "${GREEN}✓${RESET} TermTube uninstalled successfully."
exit 0
