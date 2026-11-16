# scripts/check-doc-mirrors.sh

Enforces the mirror rule in `AGENTS.md`: every non-empty file under `src/` (excluding `src/tests/`) and `scripts/`, plus `termtube` and `termtube.cmd`, needs `docs/code/<path>.md`, and every mirror needs a source.

- The source list comes from `git ls-files --cached --others --exclude-standard`, so new untracked files count and ignored files do not.
- Empty files (empty `__init__.py`) are exempt.
- Exit 1 prints two lists: sources without a mirror, mirrors without a source. Rename a file and its mirror together.
