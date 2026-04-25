#!/usr/bin/env bash
# TermTube uninstaller.

set -euo pipefail

echo -e "\033[1mTermTube Uninstaller\033[0m"
echo "This will permanently remove:"
echo "  - $HOME/.local/share/TermTube"
echo "  - $HOME/.local/bin/termtube"
echo "  - The conda/mamba 'termtube' environment (if it exists)"
echo ""
read -p "Are you sure you want to proceed? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall canceled."
    exit 0
fi

echo "Removing local files..."
# Remove the symlink first
rm -f "$HOME/.local/bin/termtube"
# Then remove the directory
rm -rf "$HOME/.local/share/TermTube"

echo "Checking for conda/mamba environments..."
if command -v mamba &>/dev/null; then
    mamba env remove -y -n termtube 2>/dev/null || true
elif command -v conda &>/dev/null; then
    conda env remove -y -n termtube 2>/dev/null || true
fi

echo -e "\033[0;32m✓\033[0m TermTube uninstalled successfully."
exit 0
