"""check-duplication.py, check-deadcode.py and gates.py."""
import unittest

from support import GateCase, has, has_node

DUP = "check-duplication.py"
DEAD = "check-deadcode.py"
GATES = "gates.py"

BLOCK = "export function {name}(items) {{\n" + "".join(
    f"  const v{n} = items.map((x) => x + {n}).filter((x) => x > {n});\n" for n in range(8)
) + "  return v0;\n}}\n"


@unittest.skipUnless(has_node("jscpd"), "jscpd not available")
class Duplication(GateCase):
    def setUp(self):
        super().setUp()
        self.configure()
        self.write("web/a.js", BLOCK.format(name="first"))
        self.assertPasses(DUP, "--init")

    def test_no_clone_passes(self):
        self.assertPasses(DUP)

    def test_a_copied_block_fails(self):
        self.write("web/b.js", BLOCK.format(name="second"))
        self.assertFails(DUP, "clones: 1 (baseline 0)", "web/b.js")
        self.assertFails(DUP, "clones", args=("--rebuild",))


class DuplicationWithoutTool(GateCase):
    def test_missing_jscpd_fails_with_the_hint(self):
        self.write(".deslop.json", '{"node_bin": []}')
        self.write("a.py", "X = 1\n")
        env = self.path_with_only("git")
        self.assertCannotRun(DUP, "jscpd is missing", "ask the owner", args=("--init",), env=env)


class DeadCode(GateCase):
    def setUp(self):
        super().setUp()
        self.configure()
        self.write("app.py", "def used():\n    return 1\n\n\nprint(used())\n")
        self.write("scripts/run.sh", "#!/bin/sh\necho run\n")
        self.write("Makefile.toml", 'run = "scripts/run.sh"\n')
        self.assertPasses(DEAD, "--init")
        self.assertPasses(DEAD)

    def test_unused_python_function_fails(self):
        self.write("b.py", "def orphan():\n    return 1\n")
        self.assertFails(DEAD, "py-unused: b.py")

    def test_unused_js_function_fails(self):
        self.write("b.js", "export function orphan() {\n  return 1;\n}\n")
        self.assertFails(DEAD, "js-unused: b.js")

    def test_unreferenced_script_fails(self):
        self.write("scripts/lonely.sh", "#!/bin/sh\necho lonely\n")
        self.write("scripts/README.md", "`scripts/lonely.sh`\n")
        self.assertFails(DEAD, "script-unreferenced: scripts/lonely.sh")

    def test_unused_and_test_only_swift_fail(self):
        self.write("Sources/App/a.swift", "func orphan() {}\nfunc probed() {}\n")
        self.write("Tests/AppTests/t.swift", "func testIt() { probed() }\n")
        self.assertFails(DEAD, "swift-unused", "swift-test-only")

    def test_list_names_each_hit(self):
        self.write("b.py", "def orphan():\n    return 1\n")
        out = self.assertPasses(DEAD, "--list")
        self.assertIn("b.py:1: nothing uses `orphan`", out)


@unittest.skipUnless(has("ruff"), "ruff not installed")
class Runner(GateCase):
    def setUp(self):
        super().setUp()
        self.configure(gates=["structure", "deadcode", "doc-size"])
        self.write("a.py", "X = 1\n")
        self.commit()

    def test_init_then_check(self):
        self.assertPasses(GATES, "--init")
        self.assertPasses(GATES)

    def test_one_failing_gate_fails_the_run(self):
        self.assertPasses(GATES, "--init")
        self.write("docs/status.md", "x" * 13000)
        self.assertFails(GATES, "doc size: failed", "structure: ok")

    def test_a_missing_baseline_cannot_run(self):
        self.assertCannotRun(GATES, "create it once with --init")

    def test_report_measures_without_writing(self):
        out = self.assertPasses(GATES, "--report")
        self.assertIn("structure:", out)
        self.assertFalse((self.root / "scripts/gate/baselines").exists())

    def test_an_unknown_gate_name_cannot_run(self):
        self.configure(gates=["structre"])
        self.assertCannotRun(GATES, "unknown gate(s)")


if __name__ == "__main__":
    unittest.main()
