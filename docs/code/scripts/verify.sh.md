# scripts/verify.sh

The commit gate from `AGENTS.md`. Runs, stopping at the first failure: `compileall` on `src`, `ruff check .` (rules and line length in `ruff.toml`), pytest on `src/tests/unit`, `integration` and `tui`, `check-doc-mirrors.sh`, `check-doc-links.py`, `check-dead-code.py`. Prints `GATE-OK` only if all passed.

- Uses `.venv/bin/ruff` if present, else `ruff` on `PATH`; the gate fails if neither exists.
- Uses `.venv/bin/python` if present, else `python3`; the latter lacks the project's dependencies, so create the venv first.
- Does not run the snapshot tests, `--test`'s wider tree, or anything that touches the network.
- Run immediately before each commit, not once per session.
