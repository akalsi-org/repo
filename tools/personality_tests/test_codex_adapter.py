from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import codex_adapter, definitions  # noqa: E402
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


def _cfg(root: pathlib.Path) -> definitions.EffectiveConfig:
  write_personality(root, "cfo", cli="codex")
  defaults = definitions.load_defaults(root)
  p = definitions.load_personality(root, "cfo")
  return definitions.resolve_effective(defaults, p)


class CodexAsRootTest(unittest.TestCase):
  def test_fresh_uses_model_effort_cd_and_seed_prompt(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = codex_adapter.as_root_argv(cfg, session_id=None, repo_root=root)
      self.assertEqual(inv.argv[0], "codex")
      self.assertIn("-m", inv.argv)
      self.assertIn("gpt-5.5", inv.argv)
      self.assertIn("-c", inv.argv)
      self.assertTrue(any("model_reasoning_effort" in a for a in inv.argv))
      self.assertIn("--cd", inv.argv)
      self.assertIn(str(root), inv.argv)
      # The seed prompt is the last positional argument.
      self.assertIn("Role context follows", inv.argv[-1])
      self.assertFalse(inv.used_native_resume)

  def test_resume_uses_resume_subcommand(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = codex_adapter.as_root_argv(cfg, session_id="abc", repo_root=root)
      self.assertEqual(inv.argv[:3], ["codex", "resume", "abc"])
      self.assertIn("-m", inv.argv)
      self.assertTrue(inv.used_native_resume)


class CodexAskTest(unittest.TestCase):
  def test_native_resume_uses_exec_resume_and_role_refresh(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      lm = pathlib.Path(tmp) / "last.txt"
      inv = codex_adapter.ask_argv(
        cfg, session_id="abc", prompt="burn?", use_replay=False,
        repo_root=root, last_message_path=lm,
      )
      self.assertEqual(inv.argv[:2], ["codex", "exec"])
      self.assertIn("--cd", inv.argv)
      self.assertIn("-o", inv.argv)
      self.assertIn(str(lm), inv.argv)
      # `resume <SESSION_ID>` chunk must appear before the prompt.
      idx = inv.argv.index("resume")
      self.assertEqual(inv.argv[idx + 1], "abc")
      self.assertIn("Role refresh", inv.argv[-1])
      self.assertIn("burn?", inv.argv[-1])
      self.assertTrue(inv.used_native_resume)

  def test_replay_fallback_drops_resume_and_uses_replay_prompt(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      lm = pathlib.Path(tmp) / "last.txt"
      inv = codex_adapter.ask_argv(
        cfg, session_id="abc", prompt="REPLAY-PROMPT", use_replay=True,
        repo_root=root, last_message_path=lm,
      )
      self.assertNotIn("resume", inv.argv)
      self.assertEqual(inv.argv[-1], "REPLAY-PROMPT")
      self.assertFalse(inv.used_native_resume)


if __name__ == "__main__":
  unittest.main()
