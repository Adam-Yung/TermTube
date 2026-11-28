# src/updater.py

Update paths for `termtube --update` and for the in-app yt-dlp refresh. Policy: nothing updates in the background; updates run on demand or when a failure suggests a stale extractor. History: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## What it updates

- Bundled tools: `bootstrap.install_all(force=True)`.
- yt-dlp and yt-dlp-ejs: `pip install -U` with the pip next to `sys.executable` (the venv's). Capped at 120 s. The running process keeps the old yt-dlp until restart.
- App code: the latest GitHub release zip replaces `src/` and `scripts/`, then `requirements.txt` is re-installed if the venv's pip exists.

## Invariants

- `VERSION == "dev"` is never overwritten. `setup.sh` writes `dev` when the checkout has no exact tag, so developer installs are safe.
- `src/` and `scripts/` are swapped through `<dir>.new` and `<dir>.old` siblings, so a failure mid-copy leaves the old tree in place. `VERSION` is written last.
- `update_app_code` decides; `_apply_release` downloads, swaps and records, and turns any failure into one `[!]` line. Quiet runs pass `_silent` instead of testing a verbose flag at each line.
- `_safe_print` degrades to ASCII because Windows consoles on cp1252 cannot encode the arrows.

## Interface

- `main.py` calls `self_update()` for `--update` and exits 0 only if it returns True. `run_all_updates` is False when the tool install, the yt-dlp upgrade or the app-code update failed. `tui/screens/mixins/feed_prompts.py` calls `update_ytdlp()` after an empty feed or an extraction error.
- `python -m src.updater --run [-v]` runs `run_all_updates` directly.

## Limits

- Release zips are not signature-checked. Release-lookup failures (rate limit, offline) are reported as "could not reach GitHub" and make `run_all_updates` return False.
- The previous version's "yt-dlp updated old -> new" toast was removed; nothing displayed it.
