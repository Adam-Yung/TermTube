# Docs map

Where each kind of document lives. `AGENTS.md` at the repo root has the rules; this is the map.

**Start here** (each session, in this order; to install or run it, `guides/setup.md`): `AGENTS.md`, `status.md`, `features/architecture.md`, `glossary.md` if a term is new, the
relevant file in `decisions/`, and the `code/` mirror of any file you are about to change.

## Top level

| File | What it is |
|---|---|
| `status.md` | What is built right now, what is not, open problems. Kept current. |
| `brief.md` | Mission, non-goals and objectives: what is worth doing. |
| `todo.md` | The next work, in order. |
| `glossary.md` | Terms used across the docs. |

## Folders

| Folder | What is in it |
|---|---|
| `features/` | One page per feature, describing the code today, indexed by objective in [the index](features/README.md): `architecture` (wiring map), `browse`, `sources`, `accounts-and-cookies`, `playback`, `library-and-downloads`, `ui`, `keybindings`, `thumbnails`, `configuration`, `install`, `quality`. |
| `code/` | One file per source file, at the same relative path (`code/src/player.py.md`): the file-specific "why". Enforced by `scripts/gate/run.sh`. |
| `decisions/` | Append-only log of implementation decisions, one file per topic. See `decisions/README.md`. |
| `guides/` | How to run, debug and check the product: `setup` (install, update, uninstall, move machines, develop, test, troubleshoot, agent recipes), `environments` (the app's venv versus the checkout's), `ci` (the GitHub jobs, including real Windows), `morning-checklist` (live checks only a human can do), `startup-debugging` (slow start or playback), `benchmarks` (source timings). |
| `plans/` | Intent for work not yet built: `website.md`, `2026-11-27-deslop-PLAN.md`. A finished plan is deleted; git keeps it. |

Which one holds a piece of information: plans describe intent, features describe the current shape of a whole feature, code docs describe
one file's reasoning, decisions record a settled call, status describes present reality, guides say how to do something.

The doc gate (`scripts/gate/docgate.py`) fails if any `docs/...` path in a doc or source file does not exist, or a feature or guide page is older than its Sources.
