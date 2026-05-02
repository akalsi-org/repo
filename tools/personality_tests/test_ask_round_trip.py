"""Full round-trip with a stub CLI runner.

The runner captures argv and emits a deterministic reply. We assert
that:
  - argv matches the adapter shape for the personality's CLI;
  - state is updated (session_id, transcript.jsonl, session_meta.yaml);
  - native-resume failure recoverable on stderr triggers replay fallback.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import runner, state, transcript  # noqa: E402
from tools.personality_pkg.commands.ask_cmd import build_parser, run  # noqa: E402
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


def _fixed_clock():
  i = [0]
  def _now():
    i[0] += 1
    return f"2026-05-01T00:00:{i[0]:02d}Z"
  return _now


class StubRunner:
  """Runner mock that records argv and emits scripted replies."""

  def __init__(self, replies):
    self.replies = list(replies)
    self.calls: list[list[str]] = []

  def __call__(self, argv):
    self.calls.append(list(argv))
    if not self.replies:
      raise AssertionError("StubRunner: no more scripted replies")
    rc, stdout, stderr = self.replies.pop(0)
    return runner.RunResult(rc=rc, stdout=stdout, stderr=stderr)


class AskRoundTripTest(unittest.TestCase):
  def test_claude_ask_fresh_writes_state_and_transcript(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      stub = StubRunner([
        (0, json.dumps({
          "result": "burn looks fine",
          "session_id": "sid-fresh",
        }), ""),
      ])
      out = io.StringIO()
      err = io.StringIO()
      rc = run(
        build_parser().parse_args(["ceo", "what's the burn?"]),
        repo_root=root, cli_runner=stub, out=out, err=err,
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      self.assertEqual(out.getvalue().strip(), "burn looks fine")
      # Argv must match Claude ask shape.
      argv = stub.calls[0]
      self.assertEqual(argv[0], "claude")
      self.assertIn("--print", argv)
      self.assertIn("--output-format", argv)
      self.assertIn("json", argv)
      # Fresh ask → no --resume
      self.assertNotIn("--resume", argv)
      # Session id captured.
      self.assertEqual(state.read_session_id(root, "ceo"), "sid-fresh")
      entries = transcript.read_entries(root, "ceo")
      kinds = [e["kind"] for e in entries]
      self.assertIn("user", kinds)
      self.assertIn("assistant", kinds)
      self.assertIn("role", kinds)
      meta = state.read_session_meta(root, "ceo")
      self.assertEqual(meta["cli"], "claude")
      self.assertEqual(meta["session_id"], "sid-fresh")

  def test_subsequent_ask_uses_native_resume(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      state.write_session_id(root, "ceo", "sid-existing")
      stub = StubRunner([
        (0, json.dumps({"result": "still fine", "session_id": "sid-existing"}), ""),
      ])
      out = io.StringIO()
      rc = run(
        build_parser().parse_args(["ceo", "still ok?"]),
        repo_root=root, cli_runner=stub, out=out, err=io.StringIO(),
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      argv = stub.calls[0]
      self.assertIn("--resume", argv)
      self.assertIn("sid-existing", argv)

  def test_native_resume_failure_falls_back_to_replay(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      state.write_session_id(root, "ceo", "stale-sid")
      stub = StubRunner([
        # First call fails with "session not found"
        (1, "", "error: session not found\n"),
        # Replay succeeds.
        (0, json.dumps({"result": "recovered", "session_id": "fresh-sid"}), ""),
      ])
      out = io.StringIO()
      err = io.StringIO()
      rc = run(
        build_parser().parse_args(["ceo", "are you back?"]),
        repo_root=root, cli_runner=stub, out=out, err=err,
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      self.assertEqual(out.getvalue().strip(), "recovered")
      self.assertEqual(len(stub.calls), 2)
      first, second = stub.calls
      self.assertIn("--resume", first)
      self.assertNotIn("--resume", second)
      # Replay-fallback transcript should record an error entry.
      entries = transcript.read_entries(root, "ceo")
      kinds = [e["kind"] for e in entries]
      self.assertIn("error", kinds)
      # Stale session_id should be cleared and the new one recorded.
      self.assertEqual(state.read_session_id(root, "ceo"), "fresh-sid")

  def test_replay_flag_forces_replay_path(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      state.write_session_id(root, "ceo", "sid-x")
      stub = StubRunner([
        (0, json.dumps({"result": "ok", "session_id": "sid-y"}), ""),
      ])
      out = io.StringIO()
      rc = run(
        build_parser().parse_args(["--replay", "ceo", "say hi"]),
        repo_root=root, cli_runner=stub, out=out, err=io.StringIO(),
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      argv = stub.calls[0]
      self.assertNotIn("--resume", argv)

  def test_codex_round_trip_uses_last_message_file(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "cfo", cli="codex")
      lm = root / ".local/personalities/cfo/last_message.txt"

      def stub(argv):
        # Simulate codex writing the final reply to -o <path>.
        idx = argv.index("-o")
        path = pathlib.Path(argv[idx + 1])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("codex reply\n", encoding="utf-8")
        return runner.RunResult(rc=0, stdout="some debug log\n", stderr="")

      out = io.StringIO()
      rc = run(
        build_parser().parse_args(["cfo", "burn?"]),
        repo_root=root, cli_runner=stub, out=out, err=io.StringIO(),
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      self.assertEqual(out.getvalue().strip(), "codex reply")

  def test_json_emit_returns_structured_payload(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      stub = StubRunner([
        (0, json.dumps({"result": "ok", "session_id": "abc"}), ""),
      ])
      out = io.StringIO()
      rc = run(
        build_parser().parse_args(["--json", "ceo", "hi"]),
        repo_root=root, cli_runner=stub, out=out, err=io.StringIO(),
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 0)
      payload = json.loads(out.getvalue())
      self.assertEqual(payload["name"], "ceo")
      self.assertEqual(payload["cli"], "claude")
      self.assertEqual(payload["reply"], "ok")
      self.assertIn("used_native_resume", payload)
      self.assertIn("used_replay", payload)

  def test_unknown_personality_returns_2(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      err = io.StringIO()
      rc = run(
        build_parser().parse_args(["ghost", "hi"]),
        repo_root=root, cli_runner=StubRunner([]),
        out=io.StringIO(), err=err,
        in_stream=io.StringIO(""), now_iso=_fixed_clock(),
      )
      self.assertEqual(rc, 2)


if __name__ == "__main__":
  unittest.main()
