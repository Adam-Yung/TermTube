"""The one config file (.deslop.json) and the repository's files as the gates see them."""
import json
from pathlib import Path

import lib

NAME = ".deslop.json"
LANGUAGES = {
    "python": (".py",),
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "typescript": (".ts", ".tsx", ".mts", ".cts"),
    "rust": (".rs",),
    "swift": (".swift",),
    "shell": (".sh", ".bash"),
    "go": (".go",),
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "c": (".c", ".h"),
    "cpp": (".cc", ".cpp", ".hpp", ".cxx"),
    "csharp": (".cs",),
    "objc": (".m", ".mm"),
    "ruby": (".rb",),
    "php": (".php",),
}
ANALYZED = ("python", "javascript", "typescript", "rust", "swift", "shell")
MARKUP = (".html", ".css", ".scss", ".sql")
TEST_DIRS = {"Tests", "tests", "test", "__tests__", "spec"}
TEST_NAMES = (".test.js", ".test.mjs", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts", "_test.py", "_test.go", "_spec.rb")
ALWAYS_OUTSIDE = ["docs", "**/node_modules", "**/__pycache__", "**/.build", "**/target"]
DEFAULTS = {
    "roots": {},
    "exclude": [],
    "unanalyzed_ok": [],
    "eslint_config": None,
    "node_bin": ["node_modules/.bin", "scripts/gate/lint/node_modules/.bin"],
    "baseline_dir": "scripts/gate/baselines",
    "mirror_dir": "docs/code",
    "feature_dir": "docs/features",
    "objectives_file": "docs/brief.md",
    "objectives_heading": "Objectives",
    "plans_dir": "docs/plans",
    "spikes_dir": "spikes",
    "growth_log": "docs/growth-log.md",
    "scripts_dir": "scripts",
    "scripts_index": "scripts/README.md",
    "doc_bytes": {"docs/status.md": 12288, "docs/todo.md": 20480},
    "gates": ["structure", "duplication", "deadcode", "mirror-fresh", "features", "doc-size", "expiry", "growth"],
    "caps": {
        "py_complexity": 10, "py_branches": 12, "py_nesting": 3,
        "js_complexity": 12, "js_depth": 3, "js_function_lines": 60,
        "rust_nesting": 4, "rust_complexity": 15, "rust_function_lines": 60,
        "swift_complexity": 10, "swift_function_lines": 40,
        "file_lines": 400, "comment_block": 3, "header_comment": 12, "clone_tokens": 70,
        "growth_lines": 300, "handoffs": 1, "dated_plans": 5,
    },
}


def merged(given):
    """The defaults overlaid with the file; a misspelt key is an error, not a silently ignored setting."""
    unknown = sorted(set(given) - set(DEFAULTS))
    unknown += sorted(f"caps.{key}" for key in set(given.get("caps", {})) - set(DEFAULTS["caps"]))
    unknown += sorted(f"roots.{key}" for key in set(given.get("roots", {})) - set(LANGUAGES))
    if unknown:
        raise lib.GateError(f"{NAME}: unknown key(s): {', '.join(unknown)}")
    out = dict(DEFAULTS, **given)
    out["caps"] = dict(DEFAULTS["caps"], **given.get("caps", {}))
    return out


def under(path, roots):
    return any(root in (".", "") or path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def is_test(path):
    parts = Path(path).parts
    name = parts[-1]
    return bool(TEST_DIRS.intersection(parts[:-1])) or name.startswith("test_") or name.endswith(TEST_NAMES)


def suffix_language(path):
    return next((lang for lang, suffixes in LANGUAGES.items() if path.endswith(suffixes)), None)


def load(path):
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError as error:
        raise lib.GateError(f"{path.name} is not valid JSON: {error}")


class Repo:
    def __init__(self, root, config_path=None):
        self.root = Path(root).resolve()
        if config_path and not config_path.is_file():
            raise lib.GateError(f"{config_path} does not exist")
        self.cfg = merged(load(config_path or self.root / NAME))
        self.caps = self.cfg["caps"]
        self._check_roots()
        self._outside = [lib.glob_pattern(g) for g in ALWAYS_OUTSIDE + self.cfg["exclude"]]
        self._files = None

    def _check_roots(self):
        for language, roots in self.cfg["roots"].items():
            missing = [r for r in roots if not (self.root / r).is_dir()]
            if missing:
                raise lib.GateError(f"{NAME}: roots.{language} names missing folder(s): {', '.join(missing)}")

    def read(self, path):
        return lib.read(self.root, path)

    def files(self):
        """Tracked and untracked (not ignored) files that exist."""
        if self._files is None:
            out = lib.git(self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
            self._files = sorted({n for n in out.split("\0") if n and (self.root / n).is_file()})
        return self._files

    def outside(self, path):
        return any(p.match(path) for p in self._outside)

    def shebang_shell(self, path):
        if "." in Path(path).name or not (self.root / path).is_file():
            return False
        with (self.root / path).open("rb") as handle:
            first = handle.readline(80)
        return first.startswith(b"#!") and first.rstrip().endswith((b"sh", b"bash"))

    def language(self, path):
        """The language of a judged source file, else None."""
        if self.outside(path):
            return None
        found = suffix_language(path) or ("shell" if self.shebang_shell(path) else None)
        if not found or not under(path, self.cfg["roots"].get(found, ["."])):
            return None
        return found

    def sources(self, *languages, tests=True):
        wanted = languages or tuple(LANGUAGES)
        return [p for p in self.files() if self.language(p) in wanted and (tests or not is_test(p))]

    def product_files(self):
        """Non-test code and markup: what features own and duplication reads."""
        markup = [p for p in self.files() if p.endswith(MARKUP) and not self.outside(p) and not is_test(p)]
        return sorted(set(self.sources(tests=False)) | set(markup))

    def node_tool(self, name):
        for folder in self.cfg["node_bin"]:
            path = self.root / folder / name
            if path.exists():
                return str(path)
        return lib.tool(name)


def open_repo(args):
    return Repo(args.root, args.config)
