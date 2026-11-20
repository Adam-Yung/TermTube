# scripts/setup.sh

macOS/Linux installer. Copies the checkout to `~/.local/share/TermTube`, builds `.venv` there, runs `python -m src.bootstrap` for deno, ffmpeg and mpv, symlinks `~/.local/bin/termtube`, writes `VERSION`, optionally creates a desktop entry (Linux) or `~/Applications/TermTube.app` (macOS). Windows counterpart: [setup.ps1](setup.ps1.md). Decisions: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## Invariants

- A full run is idempotent but heavy: `install_files` does `rm -rf` on the whole app dir, `.venv` included, so the venv is recreated and `requirements.txt` reinstalled every time (the hash cache only helps when the venv survives).
- `--refresh` is the light path: it replaces only `src`, `scripts`, `assets`, `requirements.txt`, `termtube`, `termtube.cmd` and `VERSION` in the installed copy, deletes `__pycache__`, and leaves `.venv` alone. No network, no pip, no prerequisites check, no shortcut. It refuses when no install exists and warns when `requirements.txt` differs from the hash stored in the venv (`.venv/.requirements.sha256`), telling you to run a full setup. Use it to pick up a checkout's code changes; tests: `src/tests/unit/test_setup_refresh.py` (fake `HOME`).
- `pip install` is skipped when `requirements.txt` matches the SHA256 stored in `<venv>/.requirements.sha256`; pip's resolver takes 30 to 60 s even when nothing changed. Nothing is stored outside the venv.
- `--no-prompt` (used by the `termtube` launcher's first-run auto-setup) accepts defaults and skips the desktop shortcut.
- `VERSION` is written from `git describe --tags --exact-match`, else `dev`. `dev` marks an install the updater never overwrites ([src/updater.py](../src/updater.py.md)).
- Dependency download failure is not fatal; the user is told to run `termtube --update`.

## Quirks

- The macOS app bundle's launcher has no tty when started from Finder, so it runs [launch-macos.sh](launch-macos.sh.md) with the absolute path of `~/.local/bin/termtube`. The Linux `.desktop` entry also uses that absolute path, because a desktop session's `PATH` often lacks `~/.local/bin`.
- Python is searched as `python3.13`, `3.12`, `3.11`, then `python3`, each checked for >= 3.11.

## Limits

- A full run is not run by tests; verify by hand on a clean account after changes. `--refresh` is tested with a fake `HOME`.
