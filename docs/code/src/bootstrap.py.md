# src/bootstrap.py

Downloads and installs the three bundled tools (deno, ffmpeg, mpv) into `~/.local/termtube-deps/bin/` (`%LOCALAPPDATA%\termtube-deps\bin\` on Windows). Stdlib only, so `setup.sh` can run `python -m src.bootstrap` straight after creating the venv, before any pip package exists. Version and platform per tool are recorded in `termtube-deps/versions.json`. History: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## Invariants

- `is_tool_installed`, `get_deps_dir` and `get_deps_bin` live in `src/plat.py` (stdlib, cheap to import) and are imported here. `is_tool_installed` looks only in the managed bin dir; a system copy never counts, so versions stay under our control.
- `_download` writes `<dest>.tmp` and `os.replace()`s it after a size check against `Content-Length`. An interrupted download never overwrites a working binary.
- yt-dlp is not installed here. It is a pip package, updated by `src/updater.py`.

## Platform quirks

- **mpv on macOS** is an `.app` bundle inside `mpv.tar.gz`. `Contents/MacOS/mpv` links `@executable_path/lib/`, so `bin/mpv` and `bin/lib/` must stay side by side. Copying only the binary gives a dyld error at launch.
- **mpv asset name** embeds the macOS major version (`macos-15-arm`). A release without that exact asset fails the download. When the GitHub API is rate-limited, `v0.39.0` is used.
- **mpv on Linux** has no static build. A system `mpv` is accepted (version recorded as `system`); otherwise install instructions are printed.
- **ffmpeg on macOS** comes from `eugeneware/ffmpeg-static` (`.gz` binaries, fallback tag `b6.1.1`), then `evermeet.cx` if the download fails. Linux/Windows use BtbN builds. A `.tar.xz` needs the `lzma` module; a Python built without it prints a hint.
- **Corporate proxies** that intercept HTTPS raise `CERTIFICATE_VERIFY_FAILED`. `_classify_download_error` maps that, timeouts and resets to targeted advice (`_print_download_guidance`). Certificate verification is never disabled here.
- Archives are extracted with `filter="data"` when the running Python supports it.

## Interface

- Callers: `src/deps.py` (`install_tool`), `src/updater.py` (`install_all(force=True)`), `scripts/setup.sh` and `setup.ps1` (`python -m src.bootstrap`).
- Exit code of `python -m src.bootstrap` is 0 only if every tool installed. Setup continues on failure.

## Limits

- Latest-release lookups use the unauthenticated GitHub API (60 requests/hour per IP).
- No checksum or signature verification of downloaded archives; trust rests on HTTPS and the upstream release.
