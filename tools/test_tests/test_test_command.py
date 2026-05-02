from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestCommandTest(unittest.TestCase):
  def test_plain_unittest_discovery_runs(self) -> None:
    proc = subprocess.run(
      [str(ROOT / "repo.sh"), "test", "--start-dir", "tools/targets_tests"],
      cwd=ROOT,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      check=False,
    )
    self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
  unittest.main()
