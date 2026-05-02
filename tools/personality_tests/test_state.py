from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import state  # noqa: E402
from tools.personality_tests._fixtures import make_repo  # noqa: E402


class StatePathLayoutTest(unittest.TestCase):
  def test_paths_under_local_personalities(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      d = state.state_dir(root, "ceo")
      self.assertEqual(d, root / ".local/personalities/ceo")
      self.assertEqual(state.session_id_path(root, "ceo").name, "session_id")
      self.assertEqual(state.transcript_path(root, "ceo").name, "transcript.jsonl")
      self.assertEqual(state.lock_path(root, "ceo").name, "lock")

  def test_session_id_round_trip(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      self.assertIsNone(state.read_session_id(root, "ceo"))
      state.write_session_id(root, "ceo", "abc-123")
      self.assertEqual(state.read_session_id(root, "ceo"), "abc-123")
      state.clear_session_id(root, "ceo")
      self.assertIsNone(state.read_session_id(root, "ceo"))

  def test_session_meta_round_trip(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      state.write_session_meta(root, "ceo", {
        "cli": "claude",
        "session_id": "abc",
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-01T00:00:01Z",
        "native_resume": True,
        "replay_required": False,
        "definition_sha256": "deadbeef",
        "defaults_sha256": "feedface",
      })
      meta = state.read_session_meta(root, "ceo")
      self.assertEqual(meta["cli"], "claude")
      self.assertEqual(meta["session_id"], "abc")
      self.assertTrue(meta["native_resume"])
      self.assertFalse(meta["replay_required"])


class LockSemanticsTest(unittest.TestCase):
  def test_acquire_writes_diagnostic_metadata(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      with state.acquire_lock(
        root, "ceo", mode="ask", command="personality ask ceo",
        lock_mode="fail",
      ):
        meta_text = (root / ".local/personalities/ceo/lock").read_text()
        meta = state.parse_lock_metadata(meta_text)
        self.assertEqual(meta["mode"], "ask")
        self.assertEqual(meta["command"], "personality ask ceo")
        self.assertEqual(meta["pid"], os.getpid())

  def _run_child_attempt(self, root: pathlib.Path, lock_mode: str,
                         timeout: float) -> int:
    """Run a child interpreter that tries to acquire the same lock.

    fcntl.flock contention requires a different process; spawning a
    fresh interpreter via subprocess sidesteps multiprocessing's
    forkserver bootstrapping (broken in this CPython build).
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
      f"""\
      import pathlib, sys
      sys.path.insert(0, {str(repo_root)!r})
      from tools.personality_pkg import state as st
      try:
        with st.acquire_lock(
          pathlib.Path({str(root)!r}), "ceo",
          mode="ask", command="child",
          lock_mode={lock_mode!r}, timeout={timeout},
          poll_interval=0.05,
        ):
          sys.exit(0)
      except st.LockBusy:
        sys.exit(7)
      except st.LockTimeout:
        sys.exit(8)
      """
    )
    python = os.environ.get("PYTHON") or "python3"
    proc = subprocess.run(
      [python, "-c", script],
      check=False, text=True,
      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
    )
    return proc.returncode

  def test_fail_mode_raises_on_contention(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      with state.acquire_lock(
        root, "ceo", mode="ask", command="cmd-1", lock_mode="fail",
      ):
        rc = self._run_child_attempt(root, "fail", 0.1)
        self.assertEqual(rc, 7)

  def test_wait_mode_times_out(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      with state.acquire_lock(
        root, "ceo", mode="ask", command="holder", lock_mode="fail",
      ):
        rc = self._run_child_attempt(root, "wait", 0.2)
        self.assertEqual(rc, 8)

  def test_lock_released_allows_new_acquire(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      with state.acquire_lock(
        root, "ceo", mode="ask", command="first", lock_mode="fail",
      ):
        pass
      # New caller should succeed in fail mode.
      rc = self._run_child_attempt(root, "fail", 0.1)
      self.assertEqual(rc, 0)


class ClearTest(unittest.TestCase):
  def test_clear_removes_state_dir_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      state.write_session_id(root, "ceo", "abc")
      definition = root / ".agents/personalities/ceo/personality.md"
      definition.parent.mkdir(parents=True, exist_ok=True)
      definition.write_text("dummy", encoding="utf-8")
      self.assertTrue((root / ".local/personalities/ceo").exists())
      removed = state.clear_state(root, "ceo")
      self.assertTrue(removed)
      self.assertFalse((root / ".local/personalities/ceo").exists())
      self.assertTrue(definition.exists())  # never deleted

  def test_clear_idempotent_when_absent(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      self.assertFalse(state.clear_state(root, "ceo"))


if __name__ == "__main__":
  unittest.main()
