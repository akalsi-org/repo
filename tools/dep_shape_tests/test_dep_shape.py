from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DepShapeTest(unittest.TestCase):
  def test_command_passes_current_specs(self) -> None:
    proc = subprocess.run(
      [str(ROOT / "repo.sh"), "python3", "tools/dep_shape.py"],
      cwd=ROOT,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      check=False,
    )
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertIn("python requirement blocks are pinned", proc.stdout)


if __name__ == "__main__":
  unittest.main()
