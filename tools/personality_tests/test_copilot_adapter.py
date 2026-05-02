from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import copilot_adapter, definitions  # noqa: E402
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


def _cfg(root: pathlib.Path, *, effort="null") -> definitions.EffectiveConfig:
  write_personality(root, "cto", cli="copilot", effort=effort)
  defaults = definitions.load_defaults(root)
  p = definitions.load_personality(root, "cto")
  return definitions.resolve_effective(defaults, p)


class CopilotAsRootTest(unittest.TestCase):
  def test_fresh_uses_model_and_seed(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = copilot_adapter.as_root_argv(cfg, session_id=None)
      self.assertEqual(inv.argv[0], "copilot")
      self.assertIn("--model", inv.argv)
      self.assertIn("gpt-5.4", inv.argv)
      self.assertIn("--name", inv.argv)
      self.assertIn("personality:cto", inv.argv)
      self.assertIn("-i", inv.argv)
      seed_idx = inv.argv.index("-i")
      self.assertIn("Role context follows", inv.argv[seed_idx + 1])
      self.assertFalse(inv.used_native_resume)

  def test_effort_flag_emitted(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root, effort='"medium"')
      inv = copilot_adapter.as_root_argv(cfg, session_id=None)
      self.assertIn("--reasoning-effort", inv.argv)
      self.assertIn("medium", inv.argv)

  def test_resume_uses_resume_eq_session_id(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = copilot_adapter.as_root_argv(cfg, session_id="sid-9")
      self.assertIn("--resume=sid-9", inv.argv)
      self.assertIn("--model", inv.argv)
      self.assertTrue(inv.used_native_resume)


class CopilotAskTest(unittest.TestCase):
  def test_native_resume_includes_role_refresh(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = copilot_adapter.ask_argv(
        cfg, session_id="sid-9", prompt="ship it", use_replay=False,
      )
      self.assertIn("--resume=sid-9", inv.argv)
      self.assertIn("--prompt", inv.argv)
      self.assertIn("--silent", inv.argv)
      idx = inv.argv.index("--prompt")
      self.assertIn("Role refresh", inv.argv[idx + 1])
      self.assertTrue(inv.used_native_resume)

  def test_replay_fallback_drops_resume(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = copilot_adapter.ask_argv(
        cfg, session_id="sid-9", prompt="REPLAY", use_replay=True,
      )
      self.assertFalse(any(a.startswith("--resume=") for a in inv.argv))
      self.assertIn("--prompt", inv.argv)
      idx = inv.argv.index("--prompt")
      self.assertEqual(inv.argv[idx + 1], "REPLAY")
      self.assertFalse(inv.used_native_resume)


if __name__ == "__main__":
  unittest.main()
