# src/bootstrap.py

Downloads and installs the three bundled tools (deno, ffmpeg, mpv) into `~/.local/termtube-deps/bin/` (`%LOCALAPPDATA%\termtube-deps\bin\` on Windows). Stdlib only, so `setup.sh` can run `python -m src.bootstrap` straight after creating the venv, before any pip package exists. Version and platform per tool are recorded in `termtube-deps/versions.json`. History: [docs/decisions/runtime-and-env.md](../../decisions/runtime-and-env.md).

## Invariants

- `is_tool_installed`, `get_deps_dir` and `get_deps_bin` live in `src/plat.py` (stdlib, cheap to import) and are imported here. `is_tool_installed` looks only in the managed bin dir; a system copy never counts, so versions stay under our control.
- `release_download.download` writes `<dest>.tmp` and `os.replace()`s it after a size check against `Content-Length`. An interrupted download never overwrites a working binary.
- This file decides what to install and where each binary goes; `src/release_download.py` fetches and explains failures.
- yt-dlp is not installed here. It is a pip package, updated by `src/updater.py`.

## Platform quirks

- **mpv on macOS** is an `.app` bundle inside `mpv.tar.gz`. `Contents/MacOS/mpv` links `@executable_path/lib/`, so `bin/mpv` and `bin/lib/` must stay side by side. Copying only the binary gives a dyld error at launch.
- **mpv asset name** embeds the macOS major version (`macos-15-arm`). A release without that exact asset fails the download. When the GitHub API is rate-limited, `v0.39.0` is used.
- The mpv fallback tag `v0.39.0` has no macOS asset (404), which is how a rate-limited first CI run failed.
- **mpv on Linux** has no static build. A distro `mpv` is **linked** into the managed bin dir (`bin/mpv` symlink to the real path; version recorded as `system`), because the dependency check and `player.mpv_exe` look only there. Without the link every Linux launch failed the check (a regression from the 2026-11-15 bundled-only change, found while designing the real-app CI). A real file already at `bin/mpv` is left alone; a stale link is replaced; a PATH lookup that leads back to our own link is not followed. With no mpv at all, install instructions are printed.
- **ffmpeg on macOS** comes from `eugeneware/ffmpeg-static` (`.gz` binaries, fallback tag `b6.1.1`), then `evermeet.cx` if the download fails. Linux/Windows use BtbN builds. A `.tar.xz` needs the `lzma` module; a Python built without it prints a hint.
- Archives are extracted with `filter="data"` when the running Python supports it.

## Interface

- Callers: `src/deps.py` (`install_tool`), `src/updater.py` (`install_all(force=True)`), `scripts/setup.sh` and `setup.ps1` (`python -m src.bootstrap`).
- Exit code of `python -m src.bootstrap` is 0 only if every tool installed. Setup continues on failure.

## Limits

- No checksum or signature verification of downloaded archives; trust rests on HTTPS and the upstream release.
