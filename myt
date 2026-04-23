#!/bin/bash
# MyYouTube entry point — finds the myyoutube mamba env and runs main.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Locate Python from mamba/conda environment ─────────────────────────────
find_python() {
    # 1. Try mamba/conda env directly
    if command -v conda &>/dev/null; then
        local base
        base=$(conda info --base 2>/dev/null)
        local env_python="$base/envs/myyoutube/bin/python3"
        if [[ -f "$env_python" ]]; then
            echo "$env_python"
            return 0
        fi
    fi

    # 2. Common miniforge/mambaforge locations
    for base_dir in \
        "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/opt/miniforge3" \
        "/opt/homebrew/Caskroom/miniforge/base" "/usr/local/miniforge3"
    do
        local env_python="$base_dir/envs/myyoutube/bin/python3"
        if [[ -f "$env_python" ]]; then
            echo "$env_python"
            return 0
        fi
    done

    # 3. Fall back to system python (may be missing PyYAML etc.)
    if command -v python3 &>/dev/null; then
        echo "python3"
        return 0
    fi

    echo ""
    return 1
}

PYTHON=$(find_python)

if [[ -z "$PYTHON" ]]; then
    echo "Error: Python not found. Install miniforge: https://github.com/conda-forge/miniforge"
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/src/main.py" "$@"
