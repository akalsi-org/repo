from __future__ import annotations

import os
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import lscpu


SAMPLE_VPS = """\
Architecture:                         x86_64
CPU op-mode(s):                       32-bit, 64-bit
CPU(s):                               4
Thread(s) per core:                   1
Core(s) per socket:                   4
Socket(s):                            1
"""

SAMPLE_BARE_METAL = """\
Architecture:                         x86_64
CPU(s):                               16
Thread(s) per core:                   2
Core(s) per socket:                   8
Socket(s):                            1
"""

SAMPLE_MISSING = """\
Architecture: x86_64
CPU(s): 4
"""

SAMPLE_GARBAGE = """\
Thread(s) per core: not-a-number
"""


class ThreadsPerCoreTest(unittest.TestCase):
  def test_vps_returns_one(self):
    self.assertEqual(lscpu.threads_per_core(SAMPLE_VPS), 1)

  def test_bare_metal_returns_two(self):
    self.assertEqual(lscpu.threads_per_core(SAMPLE_BARE_METAL), 2)

  def test_missing_returns_none(self):
    self.assertIsNone(lscpu.threads_per_core(SAMPLE_MISSING))

  def test_garbage_returns_none(self):
    self.assertIsNone(lscpu.threads_per_core(SAMPLE_GARBAGE))


class SmtDecisionTest(unittest.TestCase):
  def test_vps_default_skips(self):
    d = lscpu.smt_decision(SAMPLE_VPS, smt_disable_opt_in=True)
    self.assertFalse(d["apply_nosmt"])
    self.assertEqual(d["threads_per_core"], 1)

  def test_bare_metal_opt_in_applies(self):
    d = lscpu.smt_decision(SAMPLE_BARE_METAL, smt_disable_opt_in=True)
    self.assertTrue(d["apply_nosmt"])
    self.assertEqual(d["threads_per_core"], 2)

  def test_bare_metal_no_opt_in_skips(self):
    d = lscpu.smt_decision(SAMPLE_BARE_METAL, smt_disable_opt_in=False)
    self.assertFalse(d["apply_nosmt"])
    self.assertIn("did not pass", d["reason"])

  def test_missing_skips(self):
    d = lscpu.smt_decision(SAMPLE_MISSING, smt_disable_opt_in=True)
    self.assertFalse(d["apply_nosmt"])
    self.assertIsNone(d["threads_per_core"])


if __name__ == "__main__":
  unittest.main()
