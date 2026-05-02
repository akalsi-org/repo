from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import transcript  # noqa: E402
from tools.personality_tests._fixtures import make_repo  # noqa: E402


def _fixed_clock():
  i = [0]
  def _now():
    i[0] += 1
    return f"2026-05-01T00:00:{i[0]:02d}Z"
  return _now


class TranscriptAppendReplayTest(unittest.TestCase):
  def test_append_writes_one_line_per_entry(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      now = _fixed_clock()
      transcript.append_entry(root, "ceo", {
        "kind": "role",
        "definition_sha256": "deadbeef",
        "content": "you are CEO",
      }, now_iso=now)
      transcript.append_entry(root, "ceo", {
        "kind": "user", "source": "ask", "content": "burn?",
      }, now_iso=now)
      transcript.append_entry(root, "ceo", {
        "kind": "assistant", "cli": "claude", "session_id": "abc",
        "content": "burn is fine",
      }, now_iso=now)
      entries = transcript.read_entries(root, "ceo")
      self.assertEqual([e["kind"] for e in entries], ["role", "user", "assistant"])
      self.assertEqual(entries[1]["content"], "burn?")
      self.assertEqual(entries[0]["ts"], "2026-05-01T00:00:01Z")
      self.assertEqual(entries[2]["session_id"], "abc")

  def test_rejects_unknown_kind(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      with self.assertRaises(ValueError):
        transcript.append_entry(root, "ceo", {"kind": "weird", "content": "x"})

  def test_replay_prompt_contains_role_and_new_prompt(self):
    entries = [
      {"kind": "role", "ts": "t0", "content": "you are CEO"},
      {"kind": "user", "ts": "t1", "content": "first q"},
      {"kind": "assistant", "ts": "t2", "content": "first a"},
    ]
    out = transcript.build_replay_prompt(
      role_body="You are the CEO.",
      entries=entries,
      new_prompt="latest q",
      max_turns=40,
      max_bytes=200_000,
    )
    self.assertIn("Role context:", out)
    self.assertIn("You are the CEO.", out)
    self.assertIn("[user] first q", out)
    self.assertIn("[assistant] first a", out)
    self.assertIn("New prompt:", out)
    self.assertIn("latest q", out)

  def test_replay_truncates_when_too_many_turns(self):
    entries = [{"kind": "role", "content": "ROLE"}]
    for i in range(60):
      entries.append({"kind": "user", "content": f"q{i}"})
      entries.append({"kind": "assistant", "content": f"a{i}"})
    out = transcript.build_replay_prompt(
      role_body="ROLE", entries=entries, new_prompt="next",
      max_turns=10, max_bytes=200_000,
    )
    self.assertIn("earlier transcript truncated", out)
    # Earliest user turn must have been dropped.
    self.assertNotIn("q0", out)
    self.assertIn("q59", out)

  def test_replay_round_trip_is_deterministic(self):
    entries = [
      {"kind": "role", "content": "ROLE"},
      {"kind": "user", "content": "first"},
      {"kind": "assistant", "content": "second"},
    ]
    a = transcript.build_replay_prompt(
      role_body="ROLE", entries=entries, new_prompt="now",
      max_turns=40, max_bytes=200_000,
    )
    b = transcript.build_replay_prompt(
      role_body="ROLE", entries=entries, new_prompt="now",
      max_turns=40, max_bytes=200_000,
    )
    self.assertEqual(a, b)


if __name__ == "__main__":
  unittest.main()
