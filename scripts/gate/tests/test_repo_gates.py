"""check-mirror-fresh.py, check-features.py, check-expiry.py, check-growth.py and check-doc-size.py."""
import unittest

from support import GateCase

MIRROR = "check-mirror-fresh.py"
FEATURES = "check-features.py"
EXPIRY = "check-expiry.py"
SIZE = "check-doc-size.py"
GROWTH = "check-growth.py"
LOG = "docs/growth-log.md"


class Mirrors(GateCase):
    def setUp(self):
        super().setUp()
        self.write("src/a.py", "X = 1\n")
        self.write("docs/code/src/a.py.md", "# a\n")
        self.commit()

    def test_unchanged_tree_passes(self):
        self.assertPasses(MIRROR)

    def test_a_changed_source_with_a_stale_mirror_fails(self):
        self.write("src/a.py", "X = 2\n")
        self.assertFails(MIRROR, "src/a.py: changed but docs/code/src/a.py.md is not")

    def test_a_changed_mirror_passes(self):
        self.write("src/a.py", "X = 2\n")
        self.write("docs/code/src/a.py.md", "# a, two\n")
        self.assertPasses(MIRROR)

    def test_a_stamp_covers_one_version_only(self):
        self.write("src/a.py", "X = 2\n")
        self.assertPasses(MIRROR, "--stamp", "src/a.py")
        self.git("add", "docs")
        self.git("commit", "-q", "-m", "stamp")
        self.assertPasses(MIRROR)
        self.write("src/a.py", "X = 3\n")
        self.assertFails(MIRROR, "src/a.py")

    def test_a_new_source_without_a_mirror_fails(self):
        self.write("src/b.py", "Y = 1\n")
        self.assertFails(MIRROR, "no mirror docs/code/src/b.py.md")

    def test_the_framework_mirror_list_decides_what_needs_one(self):
        self.write(".framework.json", '{"mirrors": {"sources": ["src/*"], "exclude": ["src/gen*"]}}')
        self.write("tool.py", "Y = 1\n")
        self.write("src/gen.py", "Y = 1\n")
        self.assertPasses(MIRROR)


class Features(GateCase):
    PAGE = "# Core\n\n> Serves: `fast`\n> Owns: `src/core`\n"

    def setUp(self):
        super().setUp()
        self.write("docs/brief.md", "# Brief\n\n## Objectives\n\n| Id | What |\n|---|---|\n| `fast` | speed |\n")
        self.write("docs/features/README.md", "| `core.md` |\n")
        self.write("docs/features/core.md", self.PAGE)
        self.write("src/core/a.py", "X = 1\n")

    def test_every_source_claimed_passes(self):
        self.assertPasses(FEATURES)

    def test_an_unclaimed_source_fails_and_is_listed(self):
        self.write("src/extra/b.py", "Y = 1\n")
        self.assertFails(FEATURES, "src/extra/b.py: owned by no feature page")
        self.assertIn("src/extra/b.py", self.assertPasses(FEATURES, "--list-unowned"))

    def test_an_unknown_objective_fails(self):
        self.write("docs/features/core.md", self.PAGE.replace("`fast`", "`slow`"))
        self.assertFails(FEATURES, "unknown objective `slow`")

    def test_catch_all_globs_fail(self):
        for glob in ("**", "*", "src", "src/**"):
            self.write("docs/features/core.md", self.PAGE.replace("src/core", glob))
            self.assertFails(FEATURES, f"Owns `{glob}` is a catch-all")

    def test_a_glob_matching_nothing_and_a_missing_index_line_fail(self):
        self.write("docs/features/core.md", self.PAGE.replace("`src/core`", "`src/core`, `src/gone`"))
        self.write("docs/features/README.md", "# Features\n")
        self.assertFails(FEATURES, "`src/gone` matches nothing", "does not list core.md")

    def test_no_objectives_table_cannot_run(self):
        self.write("docs/brief.md", "# Brief\n")
        self.assertCannotRun(FEATURES, "no `## Objectives` table")


class Expiry(GateCase):
    def setUp(self):
        super().setUp()
        self.write("docs/plans/2026-01-01-product-HLD.md", "\n")
        self.write("docs/plans/2026-01-02-HANDOFF.md", "\n")
        for day in range(3, 8):
            self.write(f"docs/plans/2026-01-0{day}-PLAN.md", "\n")
        self.write("spikes/idea/README.md", "Kept because: it explains a decision.\n")

    def test_clean_tree_passes(self):
        self.assertPasses(EXPIRY)

    def test_a_second_handoff_fails(self):
        self.write("docs/plans/2026-01-09-HANDOFF.md", "\n")
        self.assertFails(EXPIRY, "2 handoff files")

    def test_a_sixth_dated_plan_fails(self):
        self.write("docs/plans/2026-01-08-PLAN.md", "\n")
        self.assertFails(EXPIRY, "6 dated plan files")

    def test_a_spike_without_a_reason_fails(self):
        self.write("spikes/other/a.py", "\n")
        self.assertFails(EXPIRY, "spikes/other")


class DocSize(GateCase):
    def test_the_cap_passes_and_one_byte_over_fails(self):
        self.write("docs/status.md", "x" * 12288)
        self.assertPasses(SIZE)
        self.write("docs/status.md", "x" * 12289)
        self.assertFails(SIZE, "docs/status.md")


class Growth(GateCase):
    def setUp(self):
        super().setUp()
        self.write(LOG, "# Growth log\n\n- 2026-01-01 +900: an old reason\n")
        self.write("src/a.py", "".join(f"A{n} = {n}\n" for n in range(400)))
        self.commit()

    def grow(self, lines, path="src/b.py"):
        self.write(path, "\n" * lines)

    def test_small_change_passes(self):
        self.grow(300)
        self.assertPasses(GROWTH)

    def test_large_change_without_a_new_log_line_fails(self):
        self.grow(301)
        self.assertFails(GROWTH, "+301 net source lines")

    def test_a_new_log_line_passes(self):
        self.grow(301)
        with (self.root / LOG).open("a") as log:
            log.write("- 2026-02-02 +301: a new gate\n")
        self.assertPasses(GROWTH)

    def test_tests_and_docs_do_not_count(self):
        self.grow(500, "tests/t.py")
        self.grow(500, "docs/notes.py")
        self.assertPasses(GROWTH)

    def test_a_deleted_source_offsets_new_lines(self):
        (self.root / "src/a.py").unlink()
        self.grow(500)
        self.assertPasses(GROWTH)

    def test_a_staged_rename_adds_nothing(self):
        self.git("mv", "src/a.py", "src/moved.py")
        self.assertIn("(+0 lines)", self.assertPasses(GROWTH))


if __name__ == "__main__":
    unittest.main()
