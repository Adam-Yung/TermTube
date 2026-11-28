"""Python complexity, branches and nesting by ruff, plus no def inside a def."""
import ast
import json

import lib

DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def ruff_command(caps):
    return [
        lib.tool("ruff"), "check", "--isolated", "--no-cache", "--preview", "--ignore-noqa",
        "--output-format", "json", "--select", "C901,PLR0912,PLR1702",
        "--config", f"lint.mccabe.max-complexity={caps['py_complexity']}",
        "--config", f"lint.pylint.max-branches={caps['py_branches']}",
        "--config", f"lint.pylint.max-nested-blocks={caps['py_nesting']}",
    ]


def ruff(repo, files):
    done = lib.run([*ruff_command(repo.caps), *files], repo.root, timeout=180, ok=(0, 1))
    return [
        lib.Violation(f"py:{v['code'] or 'syntax'}", lib.relative(repo.root, v["filename"]),
                      v["location"]["row"], v["message"])
        for v in json.loads(done.stdout)
    ]


def nested_defs(tree):
    """Every def that has a def among its ancestors."""
    found = []
    pending = [(tree, False)]
    while pending:
        node, inside = pending.pop()
        if inside and isinstance(node, DEFS):
            found.append(node)
        below = inside or isinstance(node, DEFS)
        pending.extend((child, below) for child in ast.iter_child_nodes(node))
    return sorted(found, key=lambda node: node.lineno)


def parse(repo, path):
    try:
        return ast.parse(repo.read(path))
    except SyntaxError as error:
        raise lib.GateError(f"{path}:{error.lineno}: does not parse")


def nested(repo, path):
    return [
        lib.Violation("py:nested-def", path, node.lineno, f"def {node.name} is inside a def")
        for node in nested_defs(parse(repo, path))
    ]


def violations(repo):
    files = repo.sources("python")
    if not files:
        return []
    return ruff(repo, files) + [item for path in files for item in nested(repo, path)]
