"""Tests for the Zig toolchain smoke (C + C++ via musl, ADR-0013).

Skip path: when ``zig`` is not on PATH the smoke must succeed with a
warning so fresh checkouts that have not bootstrapped do not fail.

Happy path: when ``zig`` is on PATH (post-bootstrap or developer-local
install) both ``zig cc`` and ``zig c++`` must compile + run a trivial
program against the native ``$REPO_ARCH-linux-musl`` target.
"""
from __future__ import annotations

import os
import shutil
import unittest
from unittest import mock

from tools.agent_check import zig_smoke
from tools.agent_check import zig_smoke_target


class ZigSmokeSkipTest(unittest.TestCase):
  def test_missing_zig_skips_cleanly(self) -> None:
    # Force shutil.which to return None inside zig_smoke so the skip path
    # is exercised even on hosts that have zig installed system-wide.
    with mock.patch("tools.agent_check.shutil.which", return_value=None):
      ok, messages = zig_smoke(zig=None)
    self.assertTrue(ok)
    self.assertEqual(len(messages), 1)
    self.assertIn("SKIP", messages[0])
    self.assertIn("zig", messages[0].lower())


class ZigSmokeTargetTest(unittest.TestCase):
  def test_target_uses_repo_arch(self) -> None:
    with mock.patch.dict(os.environ, {"REPO_ARCH": "aarch64"}):
      self.assertEqual(zig_smoke_target(), "aarch64-linux-musl")
    with mock.patch.dict(os.environ, {"REPO_ARCH": "x86_64"}):
      self.assertEqual(zig_smoke_target(), "x86_64-linux-musl")


@unittest.skipUnless(shutil.which("zig"), "zig not on PATH; smoke happy-path needs an installed toolchain")
class ZigSmokeHappyPathTest(unittest.TestCase):
  def test_c_and_cxx_compile_and_run(self) -> None:
    ok, messages = zig_smoke()
    self.assertTrue(
      ok,
      msg="zig_smoke failed:\n" + "\n".join(messages),
    )
    joined = "\n".join(messages)
    self.assertIn("c OK", joined)
    self.assertIn("c++ OK", joined)


if __name__ == "__main__":
  unittest.main()
