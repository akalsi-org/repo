from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import claude_adapter, definitions  # noqa: E402
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


def _cfg(root: pathlib.Path, *, model="null", effort="null") -> definitions.EffectiveConfig:
  write_personality(root, "ceo", cli="claude", model=model, effort=effort)
  defaults = definitions.load_defaults(root)
  p = definitions.load_personality(root, "ceo")
  return definitions.resolve_effective(defaults, p)


class ClaudeAsRootTest(unittest.TestCase):
  def test_fresh_includes_model_and_role(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = claude_adapter.as_root_argv(cfg, session_id=None)
      self.assertEqual(inv.argv[0], "claude")
      self.assertIn("--model", inv.argv)
      self.assertIn("claude-sonnet-4-6", inv.argv)
      self.assertIn("--append-system-prompt", inv.argv)
      self.assertIn("--name", inv.argv)
      self.assertIn("personality:ceo", inv.argv)
      self.assertFalse(inv.used_native_resume)

  def test_resume_uses_session_id_and_skips_model_flag(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = claude_adapter.as_root_argv(cfg, session_id="sid-123")
      self.assertIn("--resume", inv.argv)
      self.assertIn("sid-123", inv.argv)
      # On resume, claude does not need the model flag.
      self.assertNotIn("--model", inv.argv)
      self.assertTrue(inv.used_native_resume)

  def test_effort_flag_emitted_when_set(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root, effort='"high"')
      inv = claude_adapter.as_root_argv(cfg, session_id=None)
      self.assertIn("--effort", inv.argv)
      self.assertIn("high", inv.argv)


class ClaudeAskTest(unittest.TestCase):
  def test_native_resume_print_json(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = claude_adapter.ask_argv(
        cfg, session_id="sid", prompt="hello", use_replay=False,
      )
      self.assertIn("--resume", inv.argv)
      self.assertIn("sid", inv.argv)
      self.assertIn("--print", inv.argv)
      self.assertIn("--output-format", inv.argv)
      self.assertIn("json", inv.argv)
      self.assertIn("hello", inv.argv)
      self.assertTrue(inv.used_native_resume)

  def test_replay_fallback_no_resume(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      cfg = _cfg(root)
      inv = claude_adapter.ask_argv(
        cfg, session_id="sid", prompt="hi", use_replay=True,
      )
      self.assertNotIn("--resume", inv.argv)
      self.assertIn("--model", inv.argv)
      self.assertIn("claude-sonnet-4-6", inv.argv)
      self.assertFalse(inv.used_native_resume)


class ClaudeParseResponseTest(unittest.TestCase):
  def test_parses_result_and_session_id(self):
    payload = '{"result": "hi there", "session_id": "abc"}'
    text, sid = claude_adapter.parse_ask_response(payload)
    self.assertEqual(text, "hi there")
    self.assertEqual(sid, "abc")

  def test_falls_back_to_raw_text(self):
    text, sid = claude_adapter.parse_ask_response("not json")
    self.assertEqual(text, "not json")
    self.assertIsNone(sid)


if __name__ == "__main__":
  unittest.main()
