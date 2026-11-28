# Tests, gates, pipeline and developer tools

> Verified: 2026-11-28 · Sources: `scripts/verify.sh`, `scripts/check-dead-code.py`, `scripts/dev-setup.sh`, `scripts/e2e-local.py`, `scripts/gate/run.sh`, `.github/workflows/test.yml`, `.deslop.json`, `.framework.json`
> Serves: `quality`
> Owns: `scripts/verify.sh`, `scripts/check-dead-code.py`, `scripts/dev-setup.sh`, `scripts/e2e-local.py`, `scripts/smoke-ipc.py`, `scripts/canary-live.py`, `scripts/bench-sources.py`, `scripts/owner/*.py`

## What it does

One local gate, the same gate on GitHub for three systems, an end-to-end run of the installed app, a weekly live check of YouTube, and
developer tools.

## How it works

`scripts/verify.sh` byte-compiles, runs ruff and the tests, then `scripts/check-dead-code.py` and `scripts/gate/run.sh`. The gate holds
ratchets that only shrink (`.deslop.json`: structure, duplication, dead code, mirror freshness, feature ownership, doc size, expiry, growth)
and the doc gate (`.framework.json`: mirrors, links, page freshness). Pipeline layers and the canary: [../guides/ci.md](../guides/ci.md).
`scripts/dev-setup.sh` manages the checkout's venv; `scripts/bench-sources.py` times the source ladder; `scripts/owner/` holds probes only
the owner runs.

## Code

`scripts/verify.sh`, `scripts/check-dead-code.py`, `scripts/gate/`, `scripts/dev-setup.sh`, `scripts/e2e-local.py`, `scripts/smoke-ipc.py`,
`scripts/canary-live.py`, `scripts/bench-sources.py`, `scripts/owner/probe-home.py`, `scripts/owner/probe-playlist.py`, `src/tests/`.

## Rules that must hold

- Every commit passes `scripts/verify.sh`; look for `GATE-OK`.
- Tests never touch the network, the browser profile, the keychain or the real config and cache.
- A gate baseline only shrinks.

## Limits

- The ratchet gates run on Linux only in the pipeline (`DESLOP_GATES=0` elsewhere) and need `shellcheck` and `jscpd`.
- The PowerShell and `.cmd` files have no analyzer.

## How to check it

`scripts/verify.sh`; `.venv/bin/python scripts/e2e-local.py`.
