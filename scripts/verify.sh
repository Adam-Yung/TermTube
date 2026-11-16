#!/usr/bin/env bash
# The pre-commit gate from AGENTS.md: byte-compile, unit and TUI tests, doc mirrors, doc links, dead code.
# Prints GATE-OK only if every step passed.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
py=".venv/bin/python"
[[ -x $py ]] || py="python3"
"$py" -m compileall -q src
"$py" -m pytest -q src/tests/unit src/tests/integration src/tests/tui
scripts/check-doc-mirrors.sh
"$py" scripts/check-doc-links.py
"$py" scripts/check-dead-code.py
echo GATE-OK
