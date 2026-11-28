"""check-structure.py: every rule fails on a planted violation and passes clean code."""
import unittest

from support import GateCase, has, has_node

CHECK = "check-structure.py"
IGNORE = "no" + "qa"  # spelled apart so this file does not count as a suppression itself


def repeat(count, template):
    return "".join(template.format(n) for n in range(count))


class StructureCase(GateCase):
    def start(self, files, clean=None, **settings):
        """A baseline taken from a clean tree, which passes; then the planted files."""
        self.configure(**settings)
        for path, text in (clean or {}).items():
            self.write(path, text)
        self.assertPasses(CHECK, "--init")
        self.assertPasses(CHECK)
        for path, text in files.items():
            self.write(path, text)


@unittest.skipUnless(has("ruff"), "ruff not installed")
class Python(StructureCase):
    CLEAN = {"src/a.py": "def fine(x):\n    return x\n"}

    def test_complexity_and_branches_fail(self):
        body = repeat(14, "    if x == {}:\n        print(x)\n")
        self.start({"src/b.py": f"def many(x):\n{body}"}, self.CLEAN)
        self.assertFails(CHECK, "py:C901", "py:PLR0912")

    def test_deep_nesting_fails(self):
        code = ("def deep(x):\n    for a in x:\n        for b in a:\n            for c in b:\n"
                "                if c:\n                    print(c)\n")
        self.start({"src/b.py": code}, self.CLEAN)
        self.assertFails(CHECK, "py:PLR1702")

    def test_nested_def_fails(self):
        self.start({"src/b.py": "def outer():\n    def inner():\n        return 1\n    return inner\n"}, self.CLEAN)
        self.assertFails(CHECK, "py:nested-def", "src/b.py:2")

    def test_an_ignore_comment_hides_nothing_and_counts_itself(self):
        body = repeat(14, "    if x == {}:\n        print(x)\n")
        self.start({"src/b.py": f"def many(x):  # {IGNORE}\n{body}"}, self.CLEAN)
        self.assertFails(CHECK, "py:C901", "suppression")


@unittest.skipUnless(has("shellcheck"), "shellcheck not installed")
class Shell(StructureCase):
    CLEAN = {"bin/a.sh": '#!/usr/bin/env bash\nname="$1"\necho "$name"\n'}

    def test_a_dropped_quote_fails(self):
        self.start({"bin/a.sh": '#!/usr/bin/env bash\nname="$1"\nrm -f $name\n'}, self.CLEAN)
        self.assertFails(CHECK, "sh:SC2086")

    def test_a_warning_in_a_script_without_a_suffix_fails(self):
        self.start({"bin/tool": "#!/bin/bash\ncd /tmp\nunused=1\n"}, self.CLEAN)
        self.assertFails(CHECK, "sh:SC2034", "bin/tool")


class Limits(StructureCase):
    def test_comment_block_fails_but_a_header_passes(self):
        header = "# one\n# two\n# three\nX = 1\n"
        self.start({"a.rb": "x = 1\n# one\n# two\n# three\n"}, {"b.rb": header}, unanalyzed_ok=["ruby"])
        self.assertFails(CHECK, "comment-block: a.rb")

    def test_long_file_fails(self):
        self.start({"a.go": repeat(11, "var v{} = 1\n")}, unanalyzed_ok=["go"], caps={"file_lines": 10})
        self.assertFails(CHECK, "file-lines: a.go")

    def test_a_language_without_an_analyzer_is_not_silently_passed(self):
        self.configure()
        self.write("a.go", "package a\n")
        self.assertCannotRun(CHECK, "no complexity analyzer for go", args=("--init",))

    def test_absent_languages_need_no_analyzer(self):
        self.configure()
        self.write("README.md", "x\n")
        env = self.path_with_only("git")
        self.assert_status(0, CHECK, ("--init",), (), env=env)

    def test_a_missing_analyzer_fails_with_the_install_hint(self):
        self.configure()
        self.write("a.py", "X = 1\n")
        env = self.path_with_only("git")
        self.assertCannotRun(CHECK, "ruff is missing", "ask the owner", args=("--init",), env=env)

    def test_a_misspelt_config_key_is_an_error(self):
        self.configure(excludes=["x"])
        self.assertCannotRun(CHECK, "unknown key(s): excludes")

    def test_a_missing_root_is_an_error(self):
        self.configure(roots={"python": ["nowhere"]})
        self.assertCannotRun(CHECK, "names missing folder(s): nowhere")

    def test_excluded_files_are_not_judged(self):
        self.start({"third/a.rb": "x\n# a\n# b\n# c\n"}, exclude=["third"], unanalyzed_ok=["ruby"])
        self.assertPasses(CHECK)


class Ratchet(StructureCase):
    BAD = "x = 1\n# a\n# b\n# c\n"

    def setUp(self):
        super().setUp()
        self.start({}, {"a.rb": self.BAD}, unanalyzed_ok=["ruby"])

    def test_a_fall_must_be_recorded_and_cannot_come_back(self):
        self.write("a.rb", "x = 1\n")
        self.assertFails(CHECK, "run --update")
        self.assertPasses(CHECK, "--update")
        self.write("a.rb", self.BAD)
        self.assertFails(CHECK, "comment-block: a.rb: 1 (baseline 0)")

    def test_update_never_raises(self):
        self.write("b.rb", self.BAD)
        self.assertFails(CHECK, "b.rb", args=("--update",))
        self.assertFails(CHECK, "b.rb")

    def test_init_never_overwrites(self):
        self.assertCannotRun(CHECK, "never overwrites", args=("--init",))

    def test_rebuild_follows_a_moved_file(self):
        (self.root / "a.rb").rename(self.root / "moved.rb")
        self.assertFails(CHECK, "moved.rb")
        self.assertPasses(CHECK, "--rebuild")
        self.assertPasses(CHECK)

    def test_rebuild_refuses_growth(self):
        self.write("b.rb", self.BAD)
        self.assertFails(CHECK, "comment-block: total 2 (baseline 1)", args=("--rebuild",))

    def test_report_writes_nothing(self):
        before = (self.root / "scripts/gate/baselines/structure.json").read_text()
        self.write("b.rb", self.BAD)
        self.assertPasses(CHECK, "--report")
        self.assertEqual(before, (self.root / "scripts/gate/baselines/structure.json").read_text())


@unittest.skipUnless(has_node("eslint"), "eslint not available")
class JavaScript(StructureCase):
    CLEAN = {"web/a.js": "(() => {\n  function top() { return 1; }\n  top();\n})();\n"}

    def test_nested_named_function_fails(self):
        self.start({"web/b.js": "export function outer() {\n  function inner() {}\n  return inner;\n}\n"}, self.CLEAN)
        self.assertFails(CHECK, "js:no-restricted-syntax: web/b.js")

    def test_depth_complexity_and_length_fail(self):
        deep = "export function deep(x) {\n  if (x) { if (x.a) { if (x.b) { if (x.c) { return 1; } } } }\n}\n"
        wide = "export function wide(x) {\n" + repeat(13, "  if (x === {}) return 1;\n") + "  return 0;\n}\n"
        long = "export function long() {\n" + repeat(62, "  console.log({});\n") + "}\n"
        self.start({"web/b.js": deep + wide + long}, self.CLEAN)
        self.assertFails(CHECK, "js:max-depth", "js:complexity", "js:max-lines-per-function")

    def test_typescript_without_a_parser_config_cannot_run(self):
        self.configure()
        self.write("a.ts", "const a: number = 1;\n")
        self.assertCannotRun(CHECK, "eslint_config", args=("--init",))


@unittest.skipUnless(has("swiftlint"), "swiftlint not installed")
class Swift(StructureCase):
    CLEAN = {"Sources/App/a.swift": "func fine() -> Int {\n  return 1\n}\n"}

    def test_nested_function_and_long_body_fail(self):
        body = repeat(45, "  print({})\n")
        code = "func outer() {\n  func inner() {}\n  inner()\n}\n" + f"func long() {{\n{body}}}\n"
        self.start({"Sources/App/b.swift": code}, self.CLEAN)
        self.assertFails(CHECK, "swift:nesting", "swift:function_body_length")


@unittest.skipUnless(has("cargo"), "cargo not installed")
class Rust(StructureCase):
    MANIFEST = '[package]\nname = "t"\nversion = "0.1.0"\nedition = "2021"\n\n[workspace]\n'
    CLEAN = {"crate/Cargo.toml": MANIFEST, "crate/src/lib.rs": "pub fn fine() {}\n", ".gitignore": "target/\nCargo.lock\n"}

    def test_deep_nesting_fails_in_a_crate_below_the_root(self):
        code = ("pub fn deep(a: bool) -> u8 {\n    if a { if a { if a { if a { if a { return 1; } } } } }\n    0\n}\n")
        self.start({"crate/src/lib.rs": code}, self.CLEAN)
        self.assertFails(CHECK, "rust:excessive_nesting: crate/src/lib.rs")


if __name__ == "__main__":
    unittest.main()
