# scripts/dev-setup.sh

Keeps the checkout's `.venv` separate from the installed app's venv and installs development packages into the right one. Why and how the two environments differ: `docs/guides/environments.md`.

- `--check` (default) is read-only and offline. `--install` creates `.venv` if missing (`$PYTHON`, default `python3`, must be 3.11+) and runs `.venv/bin/python -m pip install -r requirements-dev.txt`. `--recreate` deletes `.venv` and installs again; it asks first unless `--yes`, and refuses if `.venv` resolves to the app venv.
- Every action goes through `.venv/bin/python`. A bare `pip` is never used: that is the mistake this script exists to prevent.
- `TERMTUBE_APP_DIR` (default `~/.local/share/TermTube`) is where the installed copy lives; tests point it at a temp dir.
- FAIL (exit 1): no venv, `.venv` is a symlink, its python has another prefix, it shares a directory with the app venv, it links into the app install, or its `pip` runs another venv's python. WARN (exit 0): `pyvenv.cfg` says the venv was created for another path (a copied venv), `ruff` or the requirements are missing.
- Tests: `src/tests/unit/test_dev_setup.py` builds throwaway venvs with `--without-pip` (no network) and checks each FAIL case.
