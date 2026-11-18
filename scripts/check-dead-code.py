#!/usr/bin/env python3
"""Fail on dead code under src/: unused imports, and functions, methods or classes nobody references.

A name counts as referenced if it appears as a name or attribute in any non-test source file, or
as an identifier inside any string (Textual binds actions and CSS ids by string). Names Textual
calls by convention (on_*, action_*, watch_*, compose, ...) are exempt. A definition referenced
only from tests is reported as test-only: the test is the only thing keeping it alive.

Usage: scripts/check-dead-code.py [--list-test-only]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CONVENTION = re.compile(r"^(on_|_on_|action_|check_action$|watch_|validate_|compute_|render|compose|emit$|main$|__)")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def py_files(tests: bool) -> list[Path]:
    return [p for p in sorted(SRC.rglob("*.py")) if ("tests" in p.parts) == tests]


def referenced_names(files: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.add(node.name.split(".")[-1])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.update(IDENT.findall(node.value))
    return names


def definitions(files: list[Path]):
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                yield path, node.name, node.lineno


def unused_imports(path: Path) -> list[tuple[int, str]]:
    if path.name == "__init__.py":
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for a in node.names:
                imported[a.asname or a.name] = node.lineno
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.update(IDENT.findall(node.value))
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        (line, name)
        for name, line in imported.items()
        if name not in used and "side-effect import" not in lines[line - 1]
    ]


def main() -> int:
    src_files, test_files = py_files(False), py_files(True)
    prod_refs = referenced_names(src_files)
    test_refs = referenced_names(test_files)
    problems: list[str] = []
    test_only: list[str] = []

    for path, name, line in definitions(src_files):
        if CONVENTION.match(name) or name in prod_refs:
            continue
        where = f"{path.relative_to(ROOT)}:{line}: {name}"
        (test_only if name in test_refs else problems).append(where)

    for path in src_files:
        for line, name in unused_imports(path):
            problems.append(f"{path.relative_to(ROOT)}:{line}: unused import {name}")

    if "--list-test-only" in sys.argv and test_only:
        print("Referenced only from tests:")
        print("\n".join(f"  {t}" for t in test_only))
    if problems:
        print("Dead code:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print(f"dead code: ok ({len(test_only)} test-only definitions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
