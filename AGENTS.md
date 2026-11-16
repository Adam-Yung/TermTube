# TermTube — Coding & Documentation Etiquette

> **HARD RULE, above everything else: never download, fetch or load a dataset, model, package or code that a platform has flagged as unsafe
> or malicious, that cannot be verified, or whose safety status you cannot read. If the platform's status cannot be read (offline, VPN, API
> error), do not download.** Do not download data or models at all without asking. Every prompt to a subagent that may touch the network
> must repeat this rule and forbid downloading. Tests must not touch the network, the user's browser profile or keychain, or kill the test
> runner (patch `_force_exit`, set `browser: none`).

> **MODEL BUDGET RULE: the token budget is very limited. Never use an Opus model. Use Sonnet (or smaller) for the main session and for every
> subagent, and set `model: "sonnet"` explicitly when spawning one. Keep heavy usage down: do the work inline when it is a few tool calls,
> spawn at most the agents the task needs, and give each a narrow brief.** Every prompt to a subagent must repeat this.

This file is the source of truth for how code and docs are written in this repo, for humans and AI agents alike.
`CLAUDE.md` and `.cursor/rules/coding-etiquette.mdc` only point here.

## Start here each session

1. **This file.**
2. **`docs/status.md`** — what is built, what is next, open problems.
3. **`docs/features/architecture.md`** — the wiring: screens, mixins, worker groups, message routing, data flows, where bugs live.
4. **`docs/glossary.md`** — skim if a term is new.
5. **`docs/decisions/`** — the topic file for whatever you are about to touch. Settled calls are recorded there; do not re-litigate them mid-task.
6. **`docs/code/<path>.md`** — the mirror of any source file before you change it.

## The goal

Code is readable end to end by a human without an AI agent. An agent is a butler, not a middleman: when asked "why is this written this
way", it answers from the docs below, not by guessing from the code.

## Project

Native Python TUI for YouTube: `Textual` UI, `yt-dlp` as a library, `mpv` over IPC, `textual-image` / PIL for thumbnails. Cold start must be
fast, the UI never blocks, and it feels like a terminal program (no fzf/gum).

- **Environment:** `venv` only. No conda or mamba. The checkout's `.venv` is separate from the installed app's; install into it only with `scripts/dev-setup.sh` (`docs/guides/environments.md`), never a bare `pip`.
- **Bundled binaries (deno, ffmpeg, mpv)** live in `~/.local/termtube-deps/bin/` (managed by `src/bootstrap.py`) and are always preferred over
  system copies. Never fall back to or prefer the system `PATH` version.
- **Network I/O** runs in `@work(thread=True, exclusive=True, group=...)` workers and reaches the UI through `self.app.call_from_thread()`.
  Components talk through Textual `Message` classes (`src/tui/messages.py`).
- **Message routing:** `self.app.post_message(msg)` does not reach screens. Use `self.app.screen.post_message(msg)`.
- **Config** is `~/.config/TermTube/config.yaml`, written only through `Config.save()`. No config file ships in the repo.
- **Python 3.11+ type hints** (`list[str]`, `X | None`).

## Documentation structure

Distinct places for distinct purposes. `docs/README.md` has the map.

- **`docs/features/<name>.md`** — one file per feature, describing its design as it exists today (not a history).
- **`docs/code/<mirror-of-source-path>.md`** — one file per source file, at the identical relative path: `src/player.py` is documented at
  `docs/code/src/player.py.md`. This is where "why is this function doing X" is answered when it is too specific for a feature doc.
  Covered: every file under `src/` except `src/tests/` and empty `__init__.py`, every file under `scripts/`, and the launchers
  `termtube` and `termtube.cmd`.
- **`docs/decisions/<topic>.md`** — append-only dated log of decisions made during implementation.
- **`docs/guides/`** — how to run, debug and check the product. **`docs/plans/`** — intent for work not yet built.
  **`docs/history/`** — finished reviews and drafts.
- Top level of `docs/`: `README.md`, `status.md`, `todo.md`, `glossary.md` only.

**Rule for agents:** before answering "why does this code do X", read the file's `docs/code/` mirror and any relevant
`docs/features/` file. Do not guess from the code alone when a doc exists.

**Rule for agents:** when code needs more than a one-line explanation, write that explanation in the `docs/code/` mirror in the *same*
change. If you cannot, say so; do not leave it silently stale.

**Doc drift:** a mirror that disagrees with its source, noticed while working on something else, is flagged to the user, not silently fixed,
unless the fix is trivial and your change depends on it.

**Mechanical checks** (run by `scripts/verify.sh`): `scripts/check-doc-mirrors.sh` (a mirror per source file, a source per mirror),
`scripts/check-doc-links.py` (every `docs/...` path mentioned exists), `scripts/check-dead-code.py` (no unused imports, no unreferenced
function, method or class).

### What a mirror contains

A mirror is not a restatement of the code. Write only what the code cannot say:

- why the file exists and what it owns (one paragraph);
- invariants, ordering constraints and threading rules a reader would break by accident;
- platform quirks and workarounds, each with the symptom that caused it;
- the non-obvious interface: who calls in, who is called, which worker group or message;
- known limits and sharp edges.

No function-by-function walk-through. If a function is clear from its name and body, it does not appear.

## Comments in code

- Comments explain **why**, never **what**. A comment that restates the next line is deleted.
- No banner comments (`# ── Section ───`), no commented-out code, no changelog comments ("removed X", "was Y").
- No multi-line comment blocks, and no docstring longer than a few lines. Longer reasoning goes in the `docs/code/` mirror.
- Comment only: a non-obvious invariant, a platform quirk or workaround, a security-relevant assumption.
- A docstring states the contract (what it returns, what it assumes) in one to three lines. Skip it when the name and signature say it all.

## Writing style (docs, comments, commit messages)

No AI slop:
- No hedging ("it's worth noting", "generally speaking").
- No restating the obvious. No filler transitions or throat-clearing.
- Active voice, concrete nouns, short sentences.
- State the fact; do not narrate how you arrived at it.

## Function and file size

- When a fix adds another special case to a function that has already collected several, extract before or alongside the fix. The trigger is
  "this function now has several unrelated concerns", not a line count.
- A file that has become a dumping ground is split by responsibility, not grown. Screens stay thin: behavior lives in mixins
  (`src/tui/screens/mixins/`) and plain modules.

## Reuse (DRY, with a YAGNI guardrail)

- Before writing new logic, check whether it exists. Consolidate real duplication; adapt the existing code to serve both call sites.
- Do not build an abstraction for reuse that does not exist yet.
- No dead code: delete deprecated functions, unused parameters and write-only attributes in the same change that orphans them.

## Testing

- **Every feature gets automated tests before it is done.** Manual verification alone does not count.
- Test behavior, not source text: no `inspect.getsource` assertions.
- **Every commit is gated on `scripts/verify.sh`** (unit and TUI tests, doc mirrors, doc links, dead-code check, ruff, byte-compile), green, run
  immediately before the commit. If it fails, fix or revert; do not commit past it.
- Tests never touch the network, the real browser profile, the keychain, or the real `~/.config` / `~/.cache`. Use the fixtures in
  `src/tests/conftest.py`.

## Keybindings

`docs/features/keybindings.md` is the only place the keymap is defined in prose; `src/tui/keymap.py` is the only place it is defined in code.
A new key goes in both, plus the help screen (`src/tui/screens/help_screen.py`) and the action bar hints, in the same change. Rules for
choosing keys are in the feature doc.

## Commits / PRs

Small, atomic, reviewable. One logical change per commit. Every commit passes the verification gate first.

## Decision log (`docs/decisions/`)

One file per topic. Entries are **append-only**: dated `## YYYY-MM-DD — title`, newest at the bottom, never edited or deleted (mark a
superseded entry by adding a later one that says so). Record decisions made during implementation: a library choice, a tradeoff, a
reversal.

## Status snapshot (`docs/status.md`)

Present reality only. Update it when a task completes or a problem changes state. `docs/todo.md` is the intended path.
