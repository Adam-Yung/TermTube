# Two environments: the app and the checkout

| | Installed app | This checkout (development) |
|---|---|---|
| Code | `~/.local/share/TermTube/` (a **copy** made by `scripts/setup.sh`: `src`, `scripts`, `assets`, a few files) | the git working tree |
| Python | `~/.local/share/TermTube/.venv` | `<repo>/.venv` |
| Run with | `termtube` (`~/.local/bin/termtube` is a symlink to `~/.local/share/TermTube/termtube`) | `./termtube` from the repo (it prefers the venv next to it), or `.venv/bin/python src/main.py` |
| Packages | `requirements.txt`, changed by `termtube --update` and `setup.sh` | `requirements-dev.txt` (adds pytest, pytest-asyncio, ruff) |
| Bundled tools | `~/.local/termtube-deps/bin/` (deno, ffmpeg, mpv) | the same directory: one set, shared on purpose |

They are separate directories with separate `site-packages`; nothing is symlinked between them. The only shared things are the bundled tools and
your config and cache (`~/.config/TermTube`, `~/.cache/termtube`). The installed copy does not follow the checkout: refresh it with
`bash scripts/setup.sh --refresh` (replaces only the code, keeps the venv, no network; it warns if `requirements.txt` changed). A full `setup.sh` run deletes and rebuilds the whole install including its venv. Their package versions drift apart (textual 8.2.5 in the checkout and 8.2.8 in the app on 2026-11-15, before the checkout's venv was rebuilt).

## The mistake to avoid

A bare `pip install ...` installs into whichever environment your shell resolves `pip` to. On 2026-11-15 that was the app's venv, so `ruff`
went into the installed app and the checkout still had none. Install into the checkout only through its interpreter:

```
scripts/dev-setup.sh --check       # report; changes nothing, no network
scripts/dev-setup.sh --install     # .venv/bin/python -m pip install -r requirements-dev.txt
scripts/dev-setup.sh --recreate    # delete .venv and rebuild it (asks first)
```

`--check` fails when `.venv` is a symlink, shares a directory with the app venv, links into the app install, or has a `pip` that belongs to
another venv. It warns when `pyvenv.cfg` shows the venv was copied from another path (the checkout's `.venv` was: its recorded creation
command names the app's path) and when `ruff` or the requirements are missing. `scripts/verify.sh` refuses to run if `.venv/bin/python` does
not belong to the checkout, and takes `RUFF=/path/to/ruff` to override which ruff it uses.
