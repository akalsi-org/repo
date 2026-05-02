from __future__ import annotations

import unittest

from tools.agent_check import pyext_smoke_issues
from tools.agent_check_tests._fixture import FixtureCase, write


class PyextSmokeTest(FixtureCase):
  def test_missing_fixture_disables_smoke(self) -> None:
    self.assertEqual(pyext_smoke_issues(self.root), [])

  def test_builder_skip_is_reported(self) -> None:
    write(
      self.root / "tests/fixtures/pyext_smoke/mod.py",
      "def add(x: int, y: int) -> int:\n  return x + y\n",
    )
    write(
      self.root / "tools/pyext-build",
      """
      #!/bin/sh
      echo 'pyext-build: skip: zig not in PATH' >&2
      exit 77
      """,
    )
    (self.root / "tools/pyext-build").chmod(0o755)
    issues = pyext_smoke_issues(self.root)
    self.assertEqual(
      issues,
      ["SKIP: pyext smoke skipped: pyext-build: skip: zig not in PATH"],
    )


if __name__ == "__main__":
  unittest.main()
