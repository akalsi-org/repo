from __future__ import annotations

import unittest

from tools.agent_check import build_report, changed_paths

from tools.agent_check_tests._fixture import FixtureCase, write


class ChangedPathsTest(FixtureCase):
  def test_untracked_directory_expands(self) -> None:
    write(self.root / "src/newmod/module.toml", "lib(name='newmod')\n")
    write(self.root / "src/newmod/foo.c", "/* x */\n")
    write(self.root / "src/newmod/foo.h", "#pragma once\n")
    write(self.root / "src/newmod/AGENTS.md", "# newmod\n")
    paths = changed_paths(self.root)
    self.assertIn("src/newmod/module.toml", paths)
    self.assertIn("src/newmod/foo.c", paths)
    self.assertIn("src/newmod/foo.h", paths)

  def test_route_advice_picks_up_expanded_files(self) -> None:
    """Regression: untracked dir → c-runtime-style route fires."""
    write(self.root / "src/newmod/module.toml", "lib(name='newmod')\n")
    write(self.root / "src/newmod/AGENTS.md", "# newmod\n")
    write(self.root / "src/newmod/loop.c", "/* x */\n")
    write(self.root / "src/newmod/tests/loop_test.c", "/* x */\n")
    report = build_report(self.root)
    # Both shallow and nested .c files must trigger the doc-sync skill via
    # `src/**/*.c` route in the fixture's index.md.
    self.assertIn("doc-sync", report.skills)
    self.assertIn("src/newmod/loop.c", report.paths)
    self.assertIn("src/newmod/tests/loop_test.c", report.paths)


class CleanRepoReportTest(FixtureCase):
  def test_untouched_repo_has_no_changes(self) -> None:
    paths = changed_paths(self.root)
    self.assertEqual(paths, [])


if __name__ == "__main__":
  unittest.main()
