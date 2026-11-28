#!/usr/bin/env bash
# The pre-commit gate from AGENTS.md: byte-compile, ruff, unit and TUI tests, dead code, ratchets, doc gate.
# Prints GATE-OK only if every step passed.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
py=".venv/bin/python"
[[ -x $py ]] || py=".venv/Scripts/python.exe"
[[ -x $py ]] || py="$(command -v python3 || command -v python)"
if [[ $py == ".venv/bin/python" ]] && [[ "$("$py" -c 'import os, sys; print(os.path.realpath(sys.prefix))')" != "$(pwd -P)/.venv" ]]; then
    echo ".venv/bin/python does not belong to this repo's .venv: run scripts/dev-setup.sh --check" >&2
    exit 1
fi
"$py" -m compileall -q src
ruff_bin="${RUFF:-.venv/bin/ruff}"
[[ -x $ruff_bin ]] || ruff_bin="$(command -v ruff || true)"
[[ -n $ruff_bin ]] || { echo "ruff not found: install it (pip install -r requirements-dev.txt)" >&2; exit 1; }
"$ruff_bin" check .
"$py" -m pytest -q src/tests/unit src/tests/integration src/tests/tui
"$py" scripts/check-dead-code.py
# The gates judge text, not platform behaviour: the pipeline runs them on Linux only (DESLOP_GATES=0 elsewhere).
if [[ ${DESLOP_GATES:-1} == 1 ]]; then PYTHON="$py" scripts/gate/run.sh; else echo "gates: skipped (DESLOP_GATES=0)"; fi
echo GATE-OK
