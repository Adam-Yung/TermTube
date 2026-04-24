#!/usr/bin/env bash
# MyYouTube entry point.
#
# Locates the Python environment created by setup.sh and runs MyYouTube.
# Search order:
#   1. .venv/  in the project directory  (created by setup.sh venv path)
#   2. 'myyoutube' conda/mamba environment
#   3. Prompt user to run setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Find Python ────────────────────────────────────────────────────────────

find_python() {
    # 1. Project-local venv (.venv/) — setup.sh fallback when conda unavailable
    local venv_py="$SCRIPT_DIR/.venv/bin/python3"
    if [[ -f "$venv_py" ]]; then
        echo "$venv_py"
        return 0
    fi

    # 2. mamba/conda 'myyoutube' environment
    local conda_base
    conda_base=$(conda info --base 2>/dev/null || true)
    for base_dir in \
        "${conda_base:+$conda_base/envs/myyoutube}" \
        "$HOME/miniforge3/envs/myyoutube" \
        "$HOME/mambaforge/envs/myyoutube" \
        "$HOME/opt/miniforge3/envs/myyoutube" \
        "/opt/homebrew/Caskroom/miniforge/base/envs/myyoutube" \
        "/usr/local/miniforge3/envs/myyoutube"
    do
        [[ -z "$base_dir" ]] && continue
        if [[ -f "$base_dir/bin/python3" ]]; then
            echo "$base_dir/bin/python3"
            return 0
        fi
    done

    return 1
}

# ── Main ───────────────────────────────────────────────────────────────────

if ! PYTHON=$(find_python 2>/dev/null); then
    echo ""
    echo -e "  \033[1;31m✗ No MyYouTube Python environment found.\033[0m"
    echo ""
    echo "  Run the one-time setup script first:"
    echo -e "    \033[1;32mbash setup.sh\033[0m"
    echo ""
    echo "  It will create a conda/venv environment and install all dependencies."
    echo ""
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/src/main.py" "$@"
