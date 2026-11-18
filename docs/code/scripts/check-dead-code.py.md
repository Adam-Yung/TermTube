# scripts/check-dead-code.py

Reports unused imports and unreferenced functions, methods and classes under `src/`. Exit 1 on any finding; part of `scripts/verify.sh`. `--list-test-only` also prints definitions that only tests reference.

## How a name counts as used

- Appears as a name, attribute or imported alias in any non-test file, or as an identifier inside any string constant. The string rule covers Textual action names and CSS ids, and also means a mention in a docstring keeps a function alive.
- Textual and Python conventions are exempt: `on_*`, `_on_*`, `action_*`, `check_action`, `watch_*`, `validate_*`, `compute_*`, `render*`, `compose*`, `main`, dunders.
- A name referenced only from `src/tests/` is "test-only": not a failure, but a sign the feature is unwired.

## Limits

- Name-based, not scope-based: two functions sharing a name protect each other, and a method called `get` is never reported.
- Imports marked `# side-effect import` and everything in `__init__.py` are skipped.
