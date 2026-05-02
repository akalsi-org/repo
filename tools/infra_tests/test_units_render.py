from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import units_render


class UnitsRenderTest(unittest.TestCase):
  def test_service_substitutes_login(self):
    out = units_render.render("gh-keys-sync.service.in", "synth-login")
    self.assertIn("https://github.com/synth-login.keys", out)
    self.assertNotIn("${LOGIN}", out)

  def test_timer_substitutes_login(self):
    out = units_render.render("gh-keys-sync.timer.in", "synth-login")
    self.assertIn("synth-login", out)
    self.assertNotIn("${LOGIN}", out)

  def test_empty_login_raises(self):
    with self.assertRaises(ValueError):
      units_render.render("gh-keys-sync.service.in", "")


if __name__ == "__main__":
  unittest.main()
