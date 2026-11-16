#!/usr/bin/env python3
"""Every `docs/...` path a document or source file mentions must exist.

The decision logs (docs/decisions/) are append-only history and are skipped; a mention that is a
pattern (contains <, *) is skipped too. Exits 1 and lists each broken reference.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKIP_DIRS = {".git", ".claude", ".venv", "__pycache__", ".pytest_cache"}
SKIP_PREFIX = ("docs/decisions/",)
EXAMPLES = {"docs/code/src/player.py.md"}
TEXT = (".md", ".py", ".sh", ".ps1", ".mdc", ".txt", ".yml", ".tcss")
PATH = re.compile(r"docs/[\w.\-/]+\.(?:md|png|py|sh|json)")


def main() -> int:
    broken = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, ROOT)
            if rel.startswith(SKIP_PREFIX) or not name.endswith(TEXT) or name == "check-doc-links.py":
                continue
            try:
                text = open(full, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            for match in PATH.finditer(text):
                path = match.group(0)
                if path in EXAMPLES or any(m in text[match.start() - 1 : match.end() + 1] for m in "<*"):
                    continue
                if not os.path.exists(os.path.join(ROOT, path)):
                    broken.append(f"{rel}: {path}")
    if broken:
        print("Broken docs/ references:")
        print("\n".join(sorted(set(broken))))
        return 1
    print("doc links: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
