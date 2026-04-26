from __future__ import annotations

import contextlib
import importlib.util
import json
import io
import pathlib
import sys
import tempfile
import unittest
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET_ID = "smooth-execution"
REVIEW_TARGET_ID = "review-loop"


def load_ideas_module():
  spec = importlib.util.spec_from_file_location("ideas_cmd", ROOT / "tools/ideas.py")
  assert spec is not None
  assert spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


ideas = load_ideas_module()


@dataclass
class RunResult:
  returncode: int
  stdout: str
  stderr: str


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
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps(
          {
            "id": TARGET_ID,
            "title": "Smooth execution",
            "owner": "ideas",
            "status": "active",
            "review_cadence": "weekly",
            "check": "./repo.sh ideas report --cost",
          }
        ),
        json.dumps(
          {
            "id": REVIEW_TARGET_ID,
            "title": "Review loop",
            "owner": "ideas",
            "status": "active",
            "review_cadence": "monthly",
            "check": "./repo.sh ideas report",
          }
        ),
      ]) + "\n",
    )

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def run_ideas(self, *args: str, check: bool = True) -> RunResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
      try:
        ideas.main(["--root", str(self.root), *args])
      except SystemExit as exc:
        if isinstance(exc.code, int):
          code = exc.code
        elif exc.code is None:
          code = 0
        else:
          print(exc.code, file=sys.stderr)
          code = 1
    proc = RunResult(code, stdout.getvalue(), stderr.getvalue())
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
      TARGET_ID,
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
      TARGET_ID,
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
      TARGET_ID,
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
      TARGET_ID,
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
      TARGET_ID,
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
      TARGET_ID,
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
      TARGET_ID,
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

  def test_add_records_daci_metadata(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "owned",
      "--title",
      "Owned idea",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--driver",
      "chief-of-staff",
      "--approver",
      "ceo",
      "--contributor",
      "ideas",
      "--contributor",
      "maintenance",
      "--informed",
      "commands",
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
    self.assertEqual(row["driver"], "chief-of-staff")
    self.assertEqual(row["approver"], "ceo")
    self.assertEqual(row["contributors"], ["ideas", "maintenance"])
    self.assertEqual(row["informed"], ["commands"])

  def test_ready_reports_conflicts_and_recommended_batch(self) -> None:
    for ident, scope in (
      ("alpha", "tools/ideas.py"),
      ("beta", "tools/ideas.py"),
      ("gamma", "tools/agent_check.py"),
    ):
      self.run_ideas(
        "add",
        "--id",
        ident,
        "--title",
        ident.title(),
        "--owner",
        "ideas",
        "--target",
        TARGET_ID,
        "--effect",
        "clear backlog",
        "--check",
        "./repo.sh ideas ready",
        "--reversibility",
        "high",
        "--maintenance",
        "L",
        "--parallel-mode",
        "safe",
        "--worktree",
        "required",
        "--write-scope",
        scope,
        "--state",
        "queued",
      )
    proc = self.run_ideas("ready")
    self.assertIn("conflict: alpha <-> beta: tools/ideas.py", proc.stdout)
    self.assertIn("recommended_batch: alpha, gamma", proc.stdout)

  def test_report_lists_blocked_decisions_and_cost_risks(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "blocked",
      "--title",
      "Blocked",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "medium",
      "--maintenance",
      "M",
      "--state",
      "shaped",
      "--decision-required",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
    )
    self.run_ideas(
      "add",
      "--id",
      "costly",
      "--title",
      "Costly",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "low",
      "--maintenance",
      "L",
      "--maintenance-overhead",
      "M",
      "--tool-sprawl",
      "H",
      "--state",
      "queued",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/agent_check.py",
    )
    proc = self.run_ideas("report", "--cost")
    self.assertIn("blocked_decisions: 1", proc.stdout)
    self.assertIn("blocked_decision: blocked owner=ideas state=shaped", proc.stdout)
    self.assertIn("cost_risk: blocked maintenance=M reversibility=medium", proc.stdout)
    self.assertIn(
      "cost_risk: costly maintenance_overhead=M tool_sprawl=H reversibility=low",
      proc.stdout,
    )
    self.assertIn(f"target: {TARGET_ID} owner=ideas", proc.stdout)
    self.assertIn("lifecycle=active_work", proc.stdout)
    self.assertIn("archive_candidate=no", proc.stdout)
    self.assertIn("review=review_missing", proc.stdout)
    self.assertIn("facet_budget: ideas", proc.stdout)

  def test_report_lists_target_review_timing(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "stale-review",
      "--title",
      "Stale review",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas report --cost",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
      "--state",
      "done",
    )
    self.run_ideas(
      "review",
      "stale-review",
      "--expected",
      "old review recorded",
      "--actual",
      "old review stored",
      "--follow-up",
      "refresh cadence",
    )
    rows = json.loads(self.run_ideas("list", "--json").stdout)["ideas"]
    rows[0]["outcome_review"]["reviewed_at"] = "2000-01-01T00:00:00+00:00"
    write(
      self.root / ".agents/ideas/ideas.jsonl",
      "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
    )
    proc = self.run_ideas("report", "--cost")
    self.assertIn(f"target: {TARGET_ID} owner=ideas", proc.stdout)
    self.assertIn("lifecycle=proved_idle", proc.stdout)
    self.assertIn("archive_candidate=yes", proc.stdout)
    self.assertIn("review=overdue", proc.stdout)
    self.assertIn("last_reviewed=2000-01-01T00:00:00+00:00", proc.stdout)
    self.assertIn("target: review-loop owner=ideas status=active active=0 done=0 blocked=0 lifecycle=idle archive_candidate=no review=review_missing", proc.stdout)

  def test_report_synthesizes_next_bet_from_archived_outcomes(self) -> None:
    archived_targets = [
      {
        "id": TARGET_ID,
        "title": "Smooth execution",
        "owner": "ideas",
        "status": "archived",
        "review_cadence": "weekly",
        "check": "./repo.sh ideas report --cost",
      },
      {
        "id": REVIEW_TARGET_ID,
        "title": "Review loop",
        "owner": "ideas",
        "status": "archived",
        "review_cadence": "monthly",
        "check": "./repo.sh ideas report",
      },
    ]
    write(
      self.root / ".agents/targets/targets.jsonl",
      "".join(json.dumps(row) + "\n" for row in archived_targets),
    )
    for ident, target, follow_up in (
      ("keep-it", TARGET_ID, "keep the current report shape"),
      ("best-next", REVIEW_TARGET_ID, "next real slice: add learning ledger from archived reviews"),
    ):
      self.run_ideas(
        "add",
        "--id",
        ident,
        "--title",
        ident,
        "--owner",
        "ideas",
        "--target",
        target,
        "--effect",
        "clear backlog",
        "--check",
        "./repo.sh ideas report --cost",
        "--reversibility",
        "high",
        "--maintenance",
        "L",
        "--parallel-mode",
        "safe",
        "--worktree",
        "required",
        "--write-scope",
        "tools/ideas.py",
        "--state",
        "queued",
      )
      self.run_ideas("promote", ident, "--state", "done")
      self.run_ideas(
        "review",
        ident,
        "--expected",
        "review captured",
        "--actual",
        "review stored",
        "--follow-up",
        follow_up,
      )
    proc = self.run_ideas("report", "--cost")
    self.assertIn("next_bet_candidate: source=best-next target=review-loop owner=ideas", proc.stdout)
    self.assertIn("action=next real slice: add learning ledger from archived reviews", proc.stdout)

  def test_report_skips_follow_up_already_addressed_by_later_work(self) -> None:
    archived_targets = [
      {
        "id": TARGET_ID,
        "title": "Smooth execution",
        "owner": "ideas",
        "status": "archived",
        "review_cadence": "weekly",
        "check": "./repo.sh ideas report --cost",
      },
    ]
    write(
      self.root / ".agents/targets/targets.jsonl",
      "".join(json.dumps(row) + "\n" for row in archived_targets),
    )
    self.run_ideas(
      "add",
      "--id",
      "source",
      "--title",
      "Source",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas report --cost",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
      "--state",
      "queued",
    )
    self.run_ideas("promote", "source", "--state", "done")
    self.run_ideas(
      "review",
      "source",
      "--expected",
      "review captured",
      "--actual",
      "review stored",
      "--follow-up",
      "next real slice: add learning ledger from archived reviews",
    )
    self.run_ideas(
      "add",
      "--id",
      "learning-ledger",
      "--title",
      "Add learning ledger",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "capture archived reviews in a learning ledger",
      "--check",
      "./repo.sh ideas report --cost",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
      "--state",
      "done",
      "--notes",
      "later work already captured the learning ledger follow-up",
    )
    self.run_ideas(
      "review",
      "learning-ledger",
      "--expected",
      "learning ledger captured",
      "--actual",
      "later work stored",
      "--follow-up",
      "keep the learning ledger narrow",
    )
    proc = self.run_ideas("report", "--cost")
    self.assertNotIn("next_bet_candidate:", proc.stdout)

  def test_report_falls_back_to_learning_ledger_when_no_strong_follow_up_remains(self) -> None:
    archived_targets = [
      {
        "id": TARGET_ID,
        "title": "Smooth execution",
        "owner": "ideas",
        "status": "archived",
        "review_cadence": "weekly",
        "check": "./repo.sh ideas report --cost",
      },
    ]
    write(
      self.root / ".agents/targets/targets.jsonl",
      "".join(json.dumps(row) + "\n" for row in archived_targets),
    )
    for ident, follow_up in (
      ("one", "keep the current report shape"),
      ("two", "delay archive mechanics until pain appears"),
      ("three", "watch for more real cycles before expanding fields"),
    ):
      self.run_ideas(
        "add",
        "--id",
        ident,
        "--title",
        ident,
        "--owner",
        "ideas",
        "--target",
        TARGET_ID,
        "--effect",
        "clear backlog",
        "--check",
        "./repo.sh ideas report --cost",
        "--reversibility",
        "high",
        "--maintenance",
        "L",
        "--parallel-mode",
        "safe",
        "--worktree",
        "required",
        "--write-scope",
        "tools/ideas.py",
        "--state",
        "queued",
      )
      self.run_ideas("promote", ident, "--state", "done")
      self.run_ideas(
        "review",
        ident,
        "--expected",
        "review captured",
        "--actual",
        "review stored",
        "--follow-up",
        follow_up,
      )
    proc = self.run_ideas("report", "--cost")
    self.assertIn("next_bet_candidate: source=archived-outcomes target=learning-ledger owner=ideas", proc.stdout)
    self.assertIn("action=add learning ledger from archived outcomes and reviews", proc.stdout)

  def test_sync_learning_ledger_writes_archived_review_rows(self) -> None:
    archived_targets = [
      {
        "id": TARGET_ID,
        "title": "Smooth execution",
        "owner": "ideas",
        "status": "archived",
        "review_cadence": "weekly",
        "check": "./repo.sh ideas report --cost",
      },
    ]
    write(
      self.root / ".agents/targets/targets.jsonl",
      "".join(json.dumps(row) + "\n" for row in archived_targets),
    )
    self.run_ideas(
      "add",
      "--id",
      "lesson-source",
      "--title",
      "Lesson source",
      "--owner",
      "ideas",
      "--target",
      TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas report --cost",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
      "--state",
      "queued",
    )
    self.run_ideas("promote", "lesson-source", "--state", "done")
    self.run_ideas(
      "review",
      "lesson-source",
      "--expected",
      "review captured",
      "--actual",
      "report now emits stable next-bet synthesis",
      "--follow-up",
      "add learning ledger from archived outcomes and reviews",
    )
    proc = self.run_ideas("sync_learning_ledger")
    self.assertIn("sync_learning_ledger: 1 rows", proc.stdout)
    rows = [
      json.loads(line)
      for line in (self.root / ".agents/kb_src/tables/learning_ledger.jsonl").read_text(encoding="utf-8").splitlines()
      if line.strip()
    ]
    self.assertEqual(rows[0]["id"], "lesson_lesson-source")
    self.assertEqual(rows[0]["target_id"], TARGET_ID)
    self.assertEqual(rows[0]["facet"], "ideas")
    self.assertEqual(rows[0]["source_artifact"], "tools/ideas.py")
    self.assertEqual(rows[0]["lesson"], "report now emits stable next-bet synthesis")

  def test_report_lists_learning_ledger_rows(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps(
        {
          "id": "lesson_one",
          "target_id": TARGET_ID,
          "facet": "ideas",
          "source_idea": "source",
          "source_artifact": "tools/ideas.py",
          "check": "./repo.sh ideas report --cost",
          "lesson": "durable lesson",
          "follow_up": "next real slice",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas("report", "--cost")
    self.assertIn("learning_ledger_rows: 1", proc.stdout)
    self.assertIn("learning_lesson: lesson_one target=smooth-execution facet=ideas check=./repo.sh ideas report --cost", proc.stdout)

  def test_unknown_target_rejected(self) -> None:
    proc = self.run_ideas(
      "add",
      "--id",
      "bad-target",
      "--title",
      "Bad target",
      "--owner",
      "ideas",
      "--target",
      "missing-target",
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas ready",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("unknown target `missing-target`", proc.stderr)

  def test_review_records_outcome(self) -> None:
    self.run_ideas(
      "add",
      "--id",
      "done-idea",
      "--title",
      "Done idea",
      "--owner",
      "ideas",
      "--target",
      REVIEW_TARGET_ID,
      "--effect",
      "clear backlog",
      "--check",
      "./repo.sh ideas report",
      "--reversibility",
      "high",
      "--maintenance",
      "L",
      "--parallel-mode",
      "safe",
      "--worktree",
      "required",
      "--write-scope",
      "tools/ideas.py",
      "--state",
      "queued",
    )
    self.run_ideas("promote", "done-idea", "--state", "done")
    self.run_ideas(
      "review",
      "done-idea",
      "--expected",
      "visible review loop",
      "--actual",
      "review stored in row",
      "--follow-up",
      "keep cadence monthly",
    )
    proc = self.run_ideas("list", "--json")
    payload = json.loads(proc.stdout)
    row = payload["ideas"][0]
    self.assertEqual(row["outcome_review"]["expected"], "visible review loop")
    self.assertEqual(row["outcome_review"]["actual"], "review stored in row")

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
      TARGET_ID,
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
