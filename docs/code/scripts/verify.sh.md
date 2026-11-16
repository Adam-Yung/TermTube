# scripts/verify.sh

The commit gate from `AGENTS.md`. Runs, stopping at the first failure: `compileall` on `src`, `ruff check .` (rules and line length in `ruff.toml`), pytest on `src/tests/unit`, `integration` and `tui`, `check-doc-mirrors.sh`, `check-doc-links.py`, `check-dead-code.py`. Prints `GATE-OK` only if all passed.

- Ruff is `$RUFF` if set, else `.venv/bin/ruff`, else `ruff` on `PATH`; the gate fails if none exists. `pip install -r requirements-dev.txt` must run with the repo's `.venv/bin/pip` (a bare `pip` may belong to another environment, such as the installed app's venv).
- Refuses to run when `.venv/bin/python` has a prefix other than this checkout's `.venv` (`scripts/dev-setup.sh --check` says why).
- Uses `.venv/bin/python` if present, else `python3`; the latter lacks the project's dependencies, so create the venv first.
- Does not run the snapshot tests, `--test`'s wider tree, or anything that touches the network.
- Run immediately before each commit, not once per session.
