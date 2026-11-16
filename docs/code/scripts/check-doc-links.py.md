# scripts/check-doc-links.py

Fails when a document or source file mentions a `docs/...` path that does not exist. Part of `scripts/verify.sh`.

- Scans `.md .py .sh .ps1 .mdc .txt .yml .tcss` under the repo root, skipping `.git`, `.claude`, `.venv` and caches.
- Skips `docs/decisions/*` files as scan sources (append-only history may name files that were later removed or moved). Mentions of decision files from elsewhere are still checked.
- Skips a mention that touches `<` or `*` (placeholders and globs) and the allow-listed example `docs/code/src/player.py.md`.
- Matches only paths ending in `.md .png .py .sh .json`. Relative links such as `../../decisions/x.md` are not checked.
