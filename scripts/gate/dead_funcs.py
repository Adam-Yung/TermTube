"""Top-level Python and JavaScript functions that no file mentions a second time."""
import ast
import re
from collections import Counter

import lib

JS_FUNCTION = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M)
# Files that can name a function without being source: configs, templates, manifests.
EXTRA = (".json", ".plist", ".toml", ".yml", ".yaml", ".html", ".cfg", ".ini")
WORD = re.compile(r"[A-Za-z_$][\w$]*")
ENTRY_NAMES = {"main", "load_tests", "setup", "teardown", "setUpModule", "tearDownModule"}


def words(repo):
    """Every identifier outside docs; experiments and tests count as users."""
    seen = Counter()
    skipped_folders = ("docs/", repo.cfg["baseline_dir"] + "/")
    sources = set(repo.sources())
    for path in repo.files():
        if not path.startswith(skipped_folders) and (path in sources or path.endswith(EXTRA)):
            seen.update(WORD.findall(repo.read(path)))
    return seen


def python_defs(repo, path):
    try:
        tree = ast.parse(repo.read(path))
    except SyntaxError as error:
        raise lib.GateError(f"{path}:{error.lineno}: does not parse")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.decorator_list:
            yield node.name, node.lineno


def js_defs(repo, path):
    text = repo.read(path)
    for found in JS_FUNCTION.finditer(text):
        yield found.group(1), text.count("\n", 0, found.start()) + 1


def skipped(name):
    return name in ENTRY_NAMES or name.startswith(("test_", "__"))


def definitions(repo):
    """(rule, name, path, line) of every function the rule judges."""
    for path in repo.sources("python", "javascript", "typescript", tests=False):
        python = repo.language(path) == "python"
        reader, rule = (python_defs, "py-unused") if python else (js_defs, "js-unused")
        for name, line in reader(repo, path):
            if not skipped(name):
                yield rule, name, path, line


def violations(repo):
    found = list(definitions(repo))
    if not found:
        return []
    defined = Counter(name for _, name, _, _ in found)
    seen = words(repo)
    return [
        lib.Violation(rule, path, line, f"nothing uses `{name}`")
        for rule, name, path, line in found
        if seen[name] <= defined[name]
    ]
