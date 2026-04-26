from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


def write(path: pathlib.Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")


class IdeasCliTest(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.root = pathlib.Path(self.tmp.name)
    write(
      self.root / ".agents/facet/ideas/facet.json",
      json.dumps(
        {
          "name": "ideas",
          "description": "Idea inventory",
          "owns": [".agents/ideas/**", "tools/ideas"],
          "commands": [{"name": "ideas", "purpose": "Manage ideas"}],
          "checks": [],
          "docs": [],
        }
      ),
    )
    write(self.root / ".agents/ideas/ideas.jsonl", "")

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def run_ideas(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
      [
        "python3",
        str(ROOT / "tools/ideas.py"),
        "--root",
        str(self.root),
        *args,
      ],
      cwd=ROOT,
      check=False,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
      self.fail(f"ideas failed: {proc.stderr}")
    return proc

  def test_add_list_and_score(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "facet-queue",
      "--title",
      "Facet queue",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
    )
    self.run_ideas(
      "score",
      "facet-queue",
      "--return",
      "H",
      "--time-sink",
      "L",
      "--go-live",
      "L",
      "--maintenance",
      "L",
      "--reversibility",
      "H",
      "--fit",
      "H",
      "--verdict",
      "Do now",
    )
    proc = self.run_ideas("list", "--json")
    payload = json.loads(proc.stdout)
    self.assertEqual(payload["ideas"][0]["score"]["verdict"], "Do now")

  def test_queue_requires_resolved_decision(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "blocked",
      "--title",
      "Blocked",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "M",
      "--state",
      "shaped",
      "--decision-required",
    )
    proc = self.run_ideas("promote", "blocked", "--state", "queued", check=False)
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("cannot queue", proc.stderr)

  def test_ready_lists_shaped_item(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "ready",
      "--title",
      "Ready idea",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      ".agents/ideas/**",
      "--state",
      "shaped",
    )
    proc = self.run_ideas("ready")
    self.assertIn("ready: Ready idea", proc.stdout)

  def test_ready_lists_queued_item_and_blockers(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "queued",
      "--title",
      "Queued idea",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      ".agents/ideas/**",
      "--state",
      "shaped",
    )
    self.run_ideas("promote", "queued", "--state", "queued")
    self.run_ideas(
      "add",
      "--id",
      "blocked",
      "--title",
      "Blocked idea",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      "--state",
      "shaped",
      "--decision-required",
    )
    proc = self.run_ideas("ready")
    self.assertIn("queued: Queued idea", proc.stdout)
    self.assertIn("parallel=safe", proc.stdout)
    self.assertIn("worktree=required", proc.stdout)
    self.assertIn("scope=.agents/ideas/**", proc.stdout)
    self.assertIn("blocked: blocked: decision required", proc.stdout)
    self.assertIn("missing parallel_mode", proc.stdout)

  def test_executable_item_without_parallel_metadata_is_blocked(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "shaped",
      "--title",
      "Shaped idea",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      "--state",
      "shaped",
    )
    proc = self.run_ideas("ready")
    self.assertIn("blocked: shaped: missing parallel_mode", proc.stdout)
    self.assertIn("missing worktree", proc.stdout)
    self.assertIn("missing write_scope", proc.stdout)

  def test_add_records_cost_fields(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "costed",
      "--title",
      "Costed idea",
      "--owner",
      "ideas",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      "--go-live-cost",
      "L",
      "--maintenance-overhead",
      "M",
      "--check-cost",
      "L",
      "--tool-sprawl",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
    )
    proc = self.run_ideas("list", "--json")
    payload = json.loads(proc.stdout)
    row = payload["ideas"][0]
    self.assertEqual(row["go_live_cost"], "L")
    self.assertEqual(row["maintenance_overhead"], "M")
    self.assertEqual(row["check_cost"], "L")
    self.assertEqual(row["tool_sprawl"], "L")
    self.assertEqual(row["parallel_mode"], "safe")
    self.assertEqual(row["worktree"], "required")
    self.assertEqual(row["write_scope"], ["tools/ideas.py"])

  def test_unknown_owner_rejected(self) -> None:
    proc = self.run_ideas(
      "add",
      "--id",
      "bad",
      "--title",
      "Bad",
      "--owner",
      "missing",
      "--target",
      "smooth execution",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "remove row",
      "--maintenance",
      "L",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("owner Facet `missing` missing", proc.stderr)
