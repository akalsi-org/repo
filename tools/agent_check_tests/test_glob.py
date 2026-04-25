from __future__ import annotations

import unittest

from tools.agent_check import glob_match


class GlobMatchTest(unittest.TestCase):
  def test_double_star_zero_segments(self) -> None:
    self.assertTrue(glob_match("src/foo.c", "src/**/*.c"))

  def test_double_star_one_segment(self) -> None:
    self.assertTrue(glob_match("src/io/loop.c", "src/**/*.c"))

  def test_double_star_many_segments(self) -> None:
    self.assertTrue(glob_match("src/io/tests/foo.c", "src/**/*.c"))

  def test_double_star_does_not_overshoot(self) -> None:
    self.assertFalse(glob_match("src/io/loop.h", "src/**/*.c"))

  def test_single_star_does_not_recurse(self) -> None:
    self.assertFalse(glob_match("src/io/loop.c", "src/*.c"))
    self.assertTrue(glob_match("src/loop.c", "src/*.c"))

  def test_exact_match(self) -> None:
    self.assertTrue(glob_match("repo.sh", "repo.sh"))

  def test_command_prefix_glob(self) -> None:
    self.assertTrue(glob_match("sample-build", "sample-*"))
    self.assertFalse(glob_match("nottool", "sample-*"))

  def test_double_star_terminal(self) -> None:
    self.assertTrue(glob_match("plans/foo.md", "plans/**"))
    self.assertTrue(glob_match("plans/sub/foo.md", "plans/**"))

  def test_brackets_question(self) -> None:
    self.assertTrue(glob_match("build", "?????"))
    self.assertFalse(glob_match("sample-build", "?????"))

  def test_pattern_anchored_to_full_path(self) -> None:
    self.assertFalse(glob_match("vendor/src/io/loop.c", "src/**/*.c"))


if __name__ == "__main__":
  unittest.main()
