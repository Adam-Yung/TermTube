# scripts/setup.sh

macOS/Linux installer. Copies the checkout to `~/.local/share/TermTube`, builds `.venv` there, runs `python -m src.bootstrap` for deno, ffmpeg and mpv, symlinks `~/.local/bin/termtube`, writes `VERSION`, optionally creates a desktop entry (Linux) or `~/Applications/TermTube.app` (macOS). Windows counterpart: [setup.ps1](setup.ps1.md). Decisions: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## Invariants

- Idempotent. `install_files` deletes and recreates the app dir, but `.venv` is rebuilt only if its pip no longer runs (interpreter moved or removed).
- `pip install` is skipped when `requirements.txt` matches the SHA256 stored in `<venv>/.requirements.sha256`; pip's resolver takes 30 to 60 s even when nothing changed. Nothing is stored outside the venv.
- `--no-prompt` (used by the `termtube` launcher's first-run auto-setup) accepts defaults and skips the desktop shortcut.
- `VERSION` is written from `git describe --tags --exact-match`, else `dev`. `dev` marks an install the updater never overwrites ([src/updater.py](../src/updater.py.md)).
- Dependency download failure is not fatal; the user is told to run `termtube --update`.

## Quirks

- The macOS app bundle's launcher calls `~/.local/bin/termtube` by absolute path, because a GUI-launched Terminal has a minimal `PATH`.
- Python is searched as `python3.13`, `3.12`, `3.11`, then `python3`, each checked for >= 3.11.

## Limits

- The help text and header comment still list yt-dlp among the binary dependencies; yt-dlp is installed by pip from `requirements.txt`.
- Not run by tests. Verify by hand on a clean account after changes.
