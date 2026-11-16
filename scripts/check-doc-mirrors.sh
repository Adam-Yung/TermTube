#!/usr/bin/env bash
# AGENTS.md rule: every source file has a mirror at docs/code/<same path>.md. Lists the files that
# do not, and mirrors whose source is gone. Exits non-zero if either list is non-empty.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

status=0
sources=$(git ls-files --cached --others --exclude-standard 'src/*' 'scripts/*' termtube termtube.cmd \
  | grep -v '^src/tests/' | grep -Ev '\.(pyc|DS_Store)$' | grep -v '__pycache__' | while read -r f; do
    [[ -s "$f" ]] && echo "$f"
  done)
missing=$(echo "$sources" | while read -r f; do [[ -f "docs/code/$f.md" ]] || echo "$f"; done)
orphans=$(cd docs/code 2>/dev/null && find . -name '*.md' | sed 's|^\./||; s|\.md$||' | while read -r f; do [[ -f "../../$f" ]] || echo "docs/code/$f.md"; done)

if [[ -n "$missing" ]]; then echo "Source files without a doc mirror:"; echo "$missing"; status=1; fi
if [[ -n "$orphans" ]]; then echo "Mirrors without a source file:"; echo "$orphans"; status=1; fi
[[ $status -eq 0 ]] && echo "doc mirrors: ok"
exit $status
