"""The gate scripts and their tests pass their own structure and dead code rules with nothing to forgive."""
import shutil
import unittest

from support import SCRIPTS, GateCase, has, has_node


@unittest.skipUnless(has("ruff") and has_node("eslint"), "ruff or eslint not available")
class SelfCheck(GateCase):
    def setUp(self):
        super().setUp()
        self.configure()
        shutil.copytree(SCRIPTS, self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))

    def test_structure_is_clean(self):
        out = self.assertPasses("check-structure.py", "--report")
        self.assertEqual(out.strip(), "structure:\n  none")


if __name__ == "__main__":
    unittest.main()
