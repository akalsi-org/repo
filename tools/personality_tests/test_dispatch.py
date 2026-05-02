from __future__ import annotations

import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import dispatch  # noqa: E402
from tools.personality_pkg.commands import (  # noqa: E402
  ask_cmd, as_root_cmd, clear_cmd, init_cmd, list_cmd,
)
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


class DispatchRouteTest(unittest.TestCase):
  def test_no_args_prints_usage_returns_2(self):
    rc = dispatch.main([])
    self.assertEqual(rc, 2)

  def test_help_returns_0(self):
    rc = dispatch.main(["help"])
    self.assertEqual(rc, 0)

  def test_unknown_subcommand_returns_2(self):
    rc = dispatch.main(["wat"])
    self.assertEqual(rc, 2)


class ListCmdTest(unittest.TestCase):
  def test_list_shows_personalities(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      write_personality(root, "cfo", cli="codex")
      buf = io.StringIO()
      rc = list_cmd.run(
        list_cmd.build_parser().parse_args([]),
        repo_root=root, out=buf,
      )
      self.assertEqual(rc, 0)
      text = buf.getvalue()
      self.assertIn("ceo", text)
      self.assertIn("cfo", text)
      self.assertIn("never", text)

  def test_list_json_output(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      buf = io.StringIO()
      rc = list_cmd.run(
        list_cmd.build_parser().parse_args(["--json"]),
        repo_root=root, out=buf,
      )
      self.assertEqual(rc, 0)
      import json
      data = json.loads(buf.getvalue())
      self.assertEqual(data[0]["name"], "ceo")
      self.assertEqual(data[0]["cli"], "claude")
      self.assertEqual(data[0]["model"], "claude-sonnet-4-6")


class InitCmdTest(unittest.TestCase):
  def test_init_creates_file(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      buf = io.StringIO()
      err = io.StringIO()
      rc = init_cmd.run(
        init_cmd.build_parser().parse_args(
          ["security-lead", "--cli", "claude"]
        ),
        repo_root=root, out=buf, err=err,
      )
      self.assertEqual(rc, 0)
      target = root / ".agents/personalities/security-lead/personality.md"
      self.assertTrue(target.exists())
      text = target.read_text()
      self.assertIn("name: security-lead", text)
      self.assertIn("cli: claude", text)

  def test_init_refuses_overwrite_without_force(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      err = io.StringIO()
      rc = init_cmd.run(
        init_cmd.build_parser().parse_args(["ceo", "--cli", "claude"]),
        repo_root=root, out=io.StringIO(), err=err,
      )
      self.assertEqual(rc, 2)
      self.assertIn("exists", err.getvalue())


class ClearCmdTest(unittest.TestCase):
  def test_clear_removes_state_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      from tools.personality_pkg import state
      state.write_session_id(root, "ceo", "abc")
      out = io.StringIO()
      rc = clear_cmd.run(
        clear_cmd.build_parser().parse_args(["ceo"]),
        repo_root=root, out=out, err=io.StringIO(),
      )
      self.assertEqual(rc, 0)
      self.assertFalse((root / ".local/personalities/ceo").exists())
      self.assertTrue((root / ".agents/personalities/ceo/personality.md").exists())

  def test_clear_unknown_personality_returns_2(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      err = io.StringIO()
      rc = clear_cmd.run(
        clear_cmd.build_parser().parse_args(["ghost"]),
        repo_root=root, out=io.StringIO(), err=err,
      )
      self.assertEqual(rc, 2)


if __name__ == "__main__":
  unittest.main()
