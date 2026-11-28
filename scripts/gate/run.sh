#!/usr/bin/env bash
# The de-slop ratchets and the doc gate. Needs ruff and shellcheck on PATH (or RUFF) and jscpd from scripts/gate/lint.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export PYTHONDONTWRITEBYTECODE=1
py="${PYTHON:-python3}"
[[ -x .venv/bin/ruff ]] && PATH="$PATH:$PWD/.venv/bin"
[[ -x scripts/gate/lint/node_modules/.bin/jscpd ]] || { echo "jscpd missing: npm ci --ignore-scripts --prefix scripts/gate/lint" >&2; exit 1; }
"$py" scripts/gate/gates.py --root .
"$py" scripts/gate/docgate.py check .
