from __future__ import annotations

import contextlib
import importlib.util
import json
import io
import pathlib
import subprocess
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
    # Set git config for tests
    subprocess.run(["git", "config", "--global", "user.name", "Test User"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "test@example.com"], check=False)
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

  def test_report_prefers_learning_ledger_receipt_with_evidence(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      "".join(
        json.dumps(row) + "\n"
        for row in [
          {
            "id": "lesson_ready_bet",
            "target_id": TARGET_ID,
            "facet": "ideas",
            "source_idea": "source",
            "source_artifact": "tools/ideas.py",
            "check": "./repo.sh ideas report --cost",
            "lesson": "operators need one cited run-now bet from repo truth",
            "follow_up": "emit one evidence-backed next bet receipt from learning ledger rows",
            "reviewed_at": "2026-04-26T12:00:00+00:00",
          },
          {
            "id": "lesson_low_signal",
            "target_id": REVIEW_TARGET_ID,
            "facet": "ideas",
            "source_idea": "weak-source",
            "source_artifact": "tools/ideas_tests/test_ideas.py",
            "check": "./repo.sh ideas report",
            "lesson": "weak lessons should not become next bets",
            "follow_up": "keep the current report shape",
            "reviewed_at": "2026-04-27T12:00:00+00:00",
          },
        ]
      ),
    )
    proc = self.run_ideas("report", "--cost")
    self.assertIn(
      "next_bet_candidate: source=lesson_ready_bet target=smooth-execution owner=ideas score=",
      proc.stdout,
    )
    self.assertIn("check=./repo.sh ideas report --cost", proc.stdout)
    self.assertIn(
      "action=emit one evidence-backed next bet receipt from learning ledger rows",
      proc.stdout,
    )
    self.assertIn(
      "next_bet_evidence: artifact=tools/ideas.py lesson=operators need one cited run-now bet from repo truth",
      proc.stdout,
    )
    self.assertIn(
      "next_bet_receipt: target=smooth-execution lesson=lesson_ready_bet "
      "source_idea=source source_artifact=tools/ideas.py "
      "expected_check=./repo.sh ideas report --cost",
      proc.stdout,
    )
    self.assertIn(
      "next_bet_reject: source=lesson_low_signal target=review-loop reason=low_score",
      proc.stdout,
    )

  def test_report_does_not_fallback_to_learning_ledger_after_ledger_exists(self) -> None:
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
          "lesson": "keep learning ledger narrow",
          "follow_up": "keep the current report shape",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas("report", "--cost")
    self.assertNotIn("next_bet_candidate:", proc.stdout)

  def test_activate_next_bet_mints_target_and_ready_idea_from_lesson(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps(
        {
          "id": "lesson_one",
          "target_id": TARGET_ID,
          "facet": "ideas",
          "source_idea": "source",
          "source_artifact": "tools/ideas.py",
          "check": "./repo.sh ideas ready",
          "lesson": "receipts need one repo-truth activation path",
          "follow_up": "mint one active target and one shaped idea from evidence",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas(
      "activate_next_bet",
      "--lesson-id",
      "lesson_one",
      "--target-id",
      "activation-target",
      "--target-title",
      "Activation target",
      "--idea-id",
      "activation-idea",
      "--idea-title",
      "Activation idea",
      "--effect",
      "Queue refills from evidence-backed repo truth",
      "--driver",
      "ideas",
      "--approver",
      "CEO",
    )
    self.assertIn("activated activation-idea from lesson_one", proc.stdout)
    ready = self.run_ideas("ready")
    self.assertIn("activation-idea: Activation idea", ready.stdout)
    targets = [
      json.loads(line)
      for line in (self.root / ".agents/targets/targets.jsonl").read_text(encoding="utf-8").splitlines()
      if line.strip()
    ]
    self.assertEqual(targets[-1]["id"], "activation-target")
    self.assertEqual(targets[-1]["status"], "active")
    ideas_rows = json.loads(self.run_ideas("list", "--json").stdout)["ideas"]
    self.assertEqual(ideas_rows[0]["target"], "activation-target")
    self.assertEqual(ideas_rows[0]["checks"], ["./repo.sh ideas ready"])
    self.assertEqual(ideas_rows[0]["write_scope"], ["tools/ideas.py"])
    self.assertIn("evidence: lesson=lesson_one", ideas_rows[0]["notes"])

  def test_activate_next_bet_fails_on_unknown_lesson(self) -> None:
    write(self.root / ".agents/kb_src/tables/learning_ledger.jsonl", "")
    proc = self.run_ideas(
      "activate_next_bet",
      "--lesson-id",
      "missing",
      "--target-id",
      "activation-target",
      "--target-title",
      "Activation target",
      "--idea-id",
      "activation-idea",
      "--idea-title",
      "Activation idea",
      "--effect",
      "Queue refills from evidence-backed repo truth",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("missing or empty", proc.stderr)

  def test_activate_next_bet_picks_single_filtered_lesson(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      "\n".join([
        json.dumps(
          {
            "id": "lesson_one",
            "target_id": TARGET_ID,
            "facet": "ideas",
            "source_idea": "source",
            "source_artifact": "tools/ideas.py",
            "check": "./repo.sh ideas ready",
            "lesson": "first lesson",
            "follow_up": "first follow up",
            "reviewed_at": "2026-04-26T12:00:00+00:00",
          }
        ),
        json.dumps(
          {
            "id": "lesson_two",
            "target_id": REVIEW_TARGET_ID,
            "facet": "ideas",
            "source_idea": "source-two",
            "source_artifact": "tools/initialize",
            "check": "./repo.sh ideas report --cost",
            "lesson": "second lesson",
            "follow_up": "second follow up",
            "reviewed_at": "2026-04-26T12:01:00+00:00",
          }
        ),
      ]) + "\n",
    )
    proc = self.run_ideas(
      "activate_next_bet",
      "--artifact",
      "initialize",
      "--target-id",
      "activation-target",
      "--target-title",
      "Activation target",
      "--idea-id",
      "activation-idea",
      "--idea-title",
      "Activation idea",
      "--effect",
      "Queue refills from evidence-backed repo truth",
    )
    self.assertIn("activated activation-idea from lesson_two", proc.stdout)
    ideas_rows = json.loads(self.run_ideas("list", "--json").stdout)["ideas"]
    self.assertEqual(ideas_rows[0]["write_scope"], ["tools/initialize"])

  def test_activate_next_bet_fails_on_ambiguous_filtered_lessons(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      "\n".join([
        json.dumps(
          {
            "id": "lesson_one",
            "target_id": TARGET_ID,
            "facet": "ideas",
            "source_idea": "source",
            "source_artifact": "tools/ideas.py",
            "check": "./repo.sh ideas ready",
            "lesson": "first lesson",
            "follow_up": "first follow up",
            "reviewed_at": "2026-04-26T12:00:00+00:00",
          }
        ),
        json.dumps(
          {
            "id": "lesson_two",
            "target_id": REVIEW_TARGET_ID,
            "facet": "ideas",
            "source_idea": "source-two",
            "source_artifact": "tools/initialize",
            "check": "./repo.sh ideas report --cost",
            "lesson": "second lesson",
            "follow_up": "second follow up",
            "reviewed_at": "2026-04-26T12:01:00+00:00",
          }
        ),
      ]) + "\n",
    )
    proc = self.run_ideas(
      "activate_next_bet",
      "--facet",
      "ideas",
      "--target-id",
      "activation-target",
      "--target-title",
      "Activation target",
      "--idea-id",
      "activation-idea",
      "--idea-title",
      "Activation idea",
      "--effect",
      "Queue refills from evidence-backed repo truth",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("activate_next_bet matched multiple lessons: lesson_one,lesson_two", proc.stderr)

  def test_activate_next_bet_scaffolds_defaults_from_lesson(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps(
        {
          "id": "lesson_scaffold",
          "target_id": TARGET_ID,
          "facet": "ideas",
          "source_idea": "auth-work",
          "source_artifact": "src/auth/handler.go",
          "check": "./repo.sh test",
          "lesson": "JWT library needs custom claims",
          "follow_up": "Add custom claims support to JWT encoder",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas(
      "activate_next_bet",
      "--lesson-id",
      "lesson_scaffold",
      "--driver",
      "ideas",
      "--approver",
      "CEO",
    )
    self.assertIn("activated auth-work-follow-up", proc.stdout)
    self.assertIn("target=smooth-execution-follow-up", proc.stdout)
    ideas_rows = json.loads(self.run_ideas("list", "--json").stdout)["ideas"]
    self.assertEqual(ideas_rows[0]["id"], "auth-work-follow-up")
    self.assertEqual(ideas_rows[0]["target"], "smooth-execution-follow-up")
    self.assertEqual(ideas_rows[0]["source_lesson"], "lesson_scaffold")
    self.assertEqual(ideas_rows[0]["source_target"], TARGET_ID)
    self.assertEqual(ideas_rows[0]["source_check"], "./repo.sh test")
    self.assertEqual(ideas_rows[0]["source_artifact"], "src/auth/handler.go")
    self.assertIn("evidence: lesson=lesson_scaffold", ideas_rows[0]["notes"])
    self.assertIn("Add custom claims support to JWT encoder", ideas_rows[0]["effect"])
    targets = [
      json.loads(line)
      for line in (self.root / ".agents/targets/targets.jsonl").read_text(encoding="utf-8").splitlines()
      if line.strip()
    ]
    self.assertEqual(targets[-1]["id"], "smooth-execution-follow-up")

  def test_lessons_lists_filtered_rows(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      "\n".join([
        json.dumps(
          {
            "id": "lesson_one",
            "target_id": TARGET_ID,
            "facet": "ideas",
            "source_idea": "source",
            "source_artifact": "tools/ideas.py",
            "check": "./repo.sh ideas ready",
            "lesson": "first lesson",
            "follow_up": "first follow up",
            "reviewed_at": "2026-04-26T12:00:00+00:00",
          }
        ),
        json.dumps(
          {
            "id": "lesson_two",
            "target_id": REVIEW_TARGET_ID,
            "facet": "ideas",
            "source_idea": "source-two",
            "source_artifact": "tools/initialize",
            "check": "./repo.sh ideas report --cost",
            "lesson": "second lesson",
            "follow_up": "second follow up",
            "reviewed_at": "2026-04-26T12:01:00+00:00",
          }
        ),
      ]) + "\n",
    )
    proc = self.run_ideas("lessons", "--artifact", "initialize", "--check", "report --cost")
    self.assertIn("lesson_two: target=review-loop facet=ideas check=./repo.sh ideas report --cost", proc.stdout)
    self.assertIn("second lesson", proc.stdout)
    self.assertIn("follow_up: second follow up", proc.stdout)
    self.assertNotIn("lesson_one:", proc.stdout)

  def test_lessons_json_returns_filtered_payload(self) -> None:
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps(
        {
          "id": "lesson_one",
          "target_id": TARGET_ID,
          "facet": "ideas",
          "source_idea": "source",
          "source_artifact": "tools/ideas.py",
          "check": "./repo.sh ideas ready",
          "lesson": "first lesson",
          "follow_up": "first follow up",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas("lessons", "--target", TARGET_ID, "--json")
    payload = json.loads(proc.stdout)
    self.assertEqual(len(payload["lessons"]), 1)
    self.assertEqual(payload["lessons"][0]["id"], "lesson_one")

  def test_lessons_fail_on_stale_learning_ledger(self) -> None:
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
      "stale-source",
      "--title",
      "Stale source",
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
    self.run_ideas("promote", "stale-source", "--state", "done")
    self.run_ideas(
      "review",
      "stale-source",
      "--expected",
      "review captured",
      "--actual",
      "new archived lesson exists",
      "--follow-up",
      "query lessons before activation",
    )
    write(self.root / ".agents/kb_src/tables/learning_ledger.jsonl", "")
    proc = self.run_ideas("lessons", check=False)
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("learning_ledger stale: missing=lesson_stale-source", proc.stderr)

  def test_report_flags_stale_learning_ledger_drift(self) -> None:
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
      "stale-source",
      "--title",
      "Stale source",
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
    self.run_ideas("promote", "stale-source", "--state", "done")
    self.run_ideas(
      "review",
      "stale-source",
      "--expected",
      "review captured",
      "--actual",
      "new archived lesson exists",
      "--follow-up",
      "query lessons before activation",
    )
    write(self.root / ".agents/kb_src/tables/learning_ledger.jsonl", "")
    proc = self.run_ideas("report", "--cost", check=False)
    self.assertIn("validation_issues: 1", proc.stdout)
    self.assertIn("issue: learning_ledger stale: missing=lesson_stale-source", proc.stdout)
    self.assertIn("run_now=./repo.sh ideas sync_learning_ledger", proc.stdout)

  def test_activate_next_bet_fails_on_stale_learning_ledger(self) -> None:
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
      "stale-source",
      "--title",
      "Stale source",
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
    self.run_ideas("promote", "stale-source", "--state", "done")
    self.run_ideas(
      "review",
      "stale-source",
      "--expected",
      "review captured",
      "--actual",
      "new archived lesson exists",
      "--follow-up",
      "query lessons before activation",
    )
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps(
        {
          "id": "lesson_old",
          "target_id": TARGET_ID,
          "facet": "ideas",
          "source_idea": "old",
          "source_artifact": "tools/ideas.py",
          "check": "./repo.sh ideas ready",
          "lesson": "old lesson",
          "follow_up": "old follow up",
          "reviewed_at": "2026-04-26T12:00:00+00:00",
        }
      ) + "\n",
    )
    proc = self.run_ideas(
      "activate_next_bet",
      "--lesson-id",
      "lesson_old",
      "--target-id",
      "activation-target",
      "--target-title",
      "Activation target",
      "--idea-id",
      "activation-idea",
      "--idea-title",
      "Activation idea",
      "--effect",
      "Queue refills from evidence-backed repo truth",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("learning_ledger stale: missing=lesson_stale-source", proc.stderr)
    self.assertIn("run_now=./repo.sh ideas sync_learning_ledger", proc.stderr)

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

  def test_shape_from_decision_creates_shaped_idea_from_board(self) -> None:
    proc = self.run_ideas(
      "shape_from_decision",
      "--id",
      "board-pick-001",
      "--title",
      "Tighten execution for alpha",
      "--recommendation",
      "Scope down alpha bet to core features",
      "--target",
      TARGET_ID,
      "--owner",
      "ideas",
      "--link",
      "board-meeting-2026-04-26",
    )
    self.assertIn("shaped board-pick-001 from board decision", proc.stdout)
    ideas_rows = json.loads(self.run_ideas("list", "--json").stdout)["ideas"]
    shaped = [r for r in ideas_rows if r["id"] == "board-pick-001"][0]
    self.assertEqual(shaped["state"], "shaped")
    self.assertEqual(shaped["title"], "Tighten execution for alpha")
    self.assertEqual(shaped["effect"], "Scope down alpha bet to core features")
    self.assertIn("board-meeting-2026-04-26", shaped["notes"])
    self.assertEqual(shaped["owner"], "ideas")
    self.assertEqual(shaped["reversibility"], "high")
    self.assertEqual(shaped["maintenance"], "L")
    ready = self.run_ideas("ready")
    self.assertIn("board-pick-001", ready.stdout)

  def test_activate_dry_run_outputs_receipt(self) -> None:
    """Test that activate_dry_run outputs a JSON receipt with no side effects."""
    # Create a target with required fields
    target_id = "test-activation"
    targets_path = self.root / ".agents/targets/targets.jsonl"
    targets_content = targets_path.read_text(encoding="utf-8")
    target_row = {
      "id": target_id,
      "title": "Test Activation",
      "owner": "ideas",
      "status": "active",
      "review_cadence": "weekly",
      "check": "./repo.sh test-check",
      "write_scope": "tools/**",
      "estimated_loe": "3d",
    }
    targets_content += json.dumps(target_row, sort_keys=True) + "\n"
    targets_path.write_text(targets_content, encoding="utf-8")
    
    # Run activate_dry_run
    proc = self.run_ideas("activate_dry_run", target_id)
    
    # Parse output
    receipt = json.loads(proc.stdout)
    
    # Verify receipt structure
    self.assertEqual(receipt["target_id"], target_id)
    self.assertEqual(receipt["check"], "./repo.sh test-check")
    self.assertEqual(receipt["write_scope"], "tools/**")
    self.assertEqual(receipt["owner_facet"], "ideas")
    self.assertEqual(receipt["estimated_loe"], "3d")
    self.assertIn("activation_command", receipt)
    self.assertIn("ready_timestamp", receipt)
    
    # Verify no side effects (target should not be activated)
    targets_rows = [json.loads(line) for line in targets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    activated_target = [r for r in targets_rows if r["id"] == target_id][0]
    self.assertNotIn("activated_at", activated_target)
    self.assertNotIn("activated_by", activated_target)

  def test_activate_updates_target_with_timestamp(self) -> None:
    """Test that activate command sets activated_at and activated_by."""
    # Create a target for activation
    target_id = "test-activate-cmd"
    targets_path = self.root / ".agents/targets/targets.jsonl"
    targets_content = targets_path.read_text(encoding="utf-8")
    target_row = {
      "id": target_id,
      "title": "Test Activate Cmd",
      "owner": "ideas",
      "status": "active",
      "review_cadence": "weekly",
      "check": "./repo.sh test",
    }
    targets_content += json.dumps(target_row, sort_keys=True) + "\n"
    targets_path.write_text(targets_content, encoding="utf-8")
    
    # Run activate
    proc = self.run_ideas("activate", "--target", target_id)
    self.assertIn("Target", proc.stdout)
    self.assertIn("activated", proc.stdout)
    
    # Verify target was updated
    targets_rows = [json.loads(line) for line in targets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    activated_target = [r for r in targets_rows if r["id"] == target_id][0]
    self.assertIn("activated_at", activated_target)
    self.assertIn("activated_by", activated_target)

  def test_archive_pass_persists_lesson(self) -> None:
    """Test that archiving with outcome=pass prompts for and records lesson."""
    # Create a target for archiving
    target_id = "test-archive-pass"
    targets_path = self.root / ".agents/targets/targets.jsonl"
    targets_content = targets_path.read_text(encoding="utf-8")
    target_row = {
      "id": target_id,
      "title": "Test Archive Pass",
      "owner": "ideas",
      "status": "active",
      "review_cadence": "weekly",
      "check": "./repo.sh test",
    }
    targets_content += json.dumps(target_row, sort_keys=True) + "\n"
    targets_path.write_text(targets_content, encoding="utf-8")
    
    # Mock input to provide lesson text
    import unittest.mock
    with unittest.mock.patch("builtins.input", return_value="test lesson learned"):
      proc = self.run_ideas("archive", target_id, "--outcome", "pass")
    
    # Verify output mentions lesson
    self.assertIn("pass", proc.stdout)
    self.assertIn("Lesson", proc.stdout)
    
    # Verify target was archived
    targets_rows = [json.loads(line) for line in targets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    archived_target = [r for r in targets_rows if r["id"] == target_id][0]
    self.assertEqual(archived_target["status"], "archived")
    self.assertEqual(archived_target["outcome"], "pass")
    self.assertIn("archived_at", archived_target)
    
    # Verify lesson was recorded
    lessons_path = self.root / ".agents/ideas/lessons.jsonl"
    if lessons_path.is_file():
      lessons = [json.loads(line) for line in lessons_path.read_text(encoding="utf-8").splitlines() if line.strip()]
      self.assertGreater(len(lessons), 0)
      lesson = lessons[0]
      self.assertEqual(lesson["lesson"], "test lesson learned")
      self.assertEqual(lesson["source_target_id"], target_id)
      self.assertEqual(lesson["outcome"], "pass")

  def test_archive_fail_marks_revisit(self) -> None:
    """Test that archiving with outcome=fail marks target for revisit."""
    # Create a target for archiving
    target_id = "test-archive-fail"
    targets_path = self.root / ".agents/targets/targets.jsonl"
    targets_content = targets_path.read_text(encoding="utf-8")
    target_row = {
      "id": target_id,
      "title": "Test Archive Fail",
      "owner": "ideas",
      "status": "active",
      "review_cadence": "weekly",
      "check": "./repo.sh test",
    }
    targets_content += json.dumps(target_row, sort_keys=True) + "\n"
    targets_path.write_text(targets_content, encoding="utf-8")
    
    # Mock input to provide failure reason
    import unittest.mock
    with unittest.mock.patch("builtins.input", return_value="test failure reason"):
      proc = self.run_ideas("archive", target_id, "--outcome", "fail")
    
    # Verify output mentions fail and revisit
    self.assertIn("fail", proc.stdout)
    self.assertIn("revisit", proc.stdout)
    
    # Verify target was archived with revisit flag
    targets_rows = [json.loads(line) for line in targets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    archived_target = [r for r in targets_rows if r["id"] == target_id][0]
    self.assertEqual(archived_target["status"], "archived")
    self.assertEqual(archived_target["outcome"], "fail")
    self.assertTrue(archived_target.get("to_revisit", False))
    self.assertIn("archived_at", archived_target)
    self.assertEqual(archived_target.get("failure_reason"), "test failure reason")

  def test_facet_budget_ceiling_blocks_activation(self) -> None:
    """Test that Facet budget ceiling prevents new idea activation."""
    # Set up repo.json with budget
    write(
      self.root / ".agents/repo.json",
      json.dumps({
        "facet_budgets": {
          "ideas": {
            "max_spend": "2 days",
            "period": "monthly",
          }
        },
        "facet_config": {},
      }),
    )
    
    # Create learning ledger
    write(
      self.root / ".agents/kb_src/tables/learning_ledger.jsonl",
      json.dumps({
        "id": "lesson_budget_test",
        "target_id": TARGET_ID,
        "facet": "ideas",
        "source_idea": "source",
        "source_artifact": "tools/ideas.py",
        "check": "./repo.sh ideas ready",
        "lesson": "budget test lesson",
        "follow_up": "test budget limit",
        "reviewed_at": "2026-04-26T12:00:00+00:00",
      }) + "\n",
    )
    
    # Create an active idea with 1 day cost estimate
    write(
      self.root / ".agents/ideas/ideas.jsonl",
      json.dumps({
        "id": "active-idea-1",
        "title": "Active idea 1",
        "owner": "ideas",
        "state": "active",
        "target": TARGET_ID,
        "effect": "test effect",
        "checks": ["./repo.sh ideas ready"],
        "reversibility": "high",
        "maintenance": "L",
        "decision_required": False,
        "cost_estimate": 1.0,
        "created_at": "2026-04-26T00:00:00+00:00",
        "updated_at": "2026-04-26T00:00:00+00:00",
      }) + "\n",
    )
    
    # Create a second active idea with 1 day cost estimate (total 2 days at budget ceiling)
    ideas_path = self.root / ".agents/ideas/ideas.jsonl"
    ideas_content = ideas_path.read_text(encoding="utf-8")
    ideas_content += json.dumps({
      "id": "active-idea-2",
      "title": "Active idea 2",
      "owner": "ideas",
      "state": "active",
      "target": REVIEW_TARGET_ID,
      "effect": "test effect",
      "checks": ["./repo.sh ideas ready"],
      "reversibility": "high",
      "maintenance": "L",
      "decision_required": False,
      "cost_estimate": 1.0,
      "created_at": "2026-04-26T00:00:00+00:00",
      "updated_at": "2026-04-26T00:00:00+00:00",
    }) + "\n"
    ideas_path.write_text(ideas_content, encoding="utf-8")
    
    # Try to activate new idea with 1 day cost estimate - should fail
    proc = self.run_ideas(
      "activate_next_bet",
      "--lesson-id",
      "lesson_budget_test",
      "--target-id",
      "budget-test-target",
      "--target-title",
      "Budget test target",
      "--idea-id",
      "budget-test-idea",
      "--idea-title",
      "Budget test idea",
      "--effect",
      "test budget enforcement",
      "--cost-estimate",
      "1.0",
      check=False,
    )
    self.assertNotEqual(proc.returncode, 0)
    self.assertIn("Facet budget ceiling exceeded", proc.stderr)
    self.assertIn("active-idea-1", proc.stderr)
    self.assertIn("active-idea-2", proc.stderr)


class BatchSafeParallelTest(unittest.TestCase):
  """Tests for safe parallel batch computation."""

  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.root = pathlib.Path(self.tmp.name)
    # Set git config for tests
    subprocess.run(["git", "config", "--global", "user.name", "Test User"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "test@example.com"], check=False)
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

  def test_safe_parallel_batch_detects_write_scope_conflicts(self) -> None:
    """Batch should exclude targets with overlapping write_scope."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-a",
          "title": "Target A",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-b",
          "title": "Target B",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/tools/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-c",
          "title": "Target C",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["docs/**"],
          "parallel_mode": "safe",
        }),
      ]) + "\n",
    )
    ledger = ideas.load_target_ledger(self.root)
    batch = ideas.compute_safe_parallel_batch(ledger)
    batch_ids = {t.id for t in batch}
    
    # Should pick largest valid batch: either [a, c] or [b, c]
    # Both are valid (no conflicts), so algorithm picks one with size 2
    self.assertEqual(len(batch), 2)
    self.assertIn("target-c", batch_ids)
    # Either target-a or target-b should be in batch, but not both
    self.assertTrue("target-a" in batch_ids or "target-b" in batch_ids)
    self.assertFalse("target-a" in batch_ids and "target-b" in batch_ids)

  def test_safe_parallel_batch_respects_serial_mode(self) -> None:
    """Batch should exclude serial targets and only include safe ones."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-safe-1",
          "title": "Target Safe 1",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["docs/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-safe-2",
          "title": "Target Safe 2",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["ideas/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-serial",
          "title": "Target Serial",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/**"],
          "parallel_mode": "serial",
        }),
      ]) + "\n",
    )
    ledger = ideas.load_target_ledger(self.root)
    batch = ideas.compute_safe_parallel_batch(ledger)
    batch_ids = {t.id for t in batch}
    
    self.assertNotIn("target-serial", batch_ids)
    self.assertEqual(len(batch), 2)
    self.assertIn("target-safe-1", batch_ids)
    self.assertIn("target-safe-2", batch_ids)

  def test_safe_parallel_batch_detects_blocked_targets(self) -> None:
    """Batch should exclude blocked targets waiting for other targets."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-base",
          "title": "Target Base",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-blocked",
          "title": "Target Blocked",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["docs/**"],
          "parallel_mode": "blocked",
          "blocker_target_id": "target-base",
        }),
      ]) + "\n",
    )
    ledger = ideas.load_target_ledger(self.root)
    batch = ideas.compute_safe_parallel_batch(ledger)
    batch_ids = {t.id for t in batch}
    
    self.assertNotIn("target-blocked", batch_ids)

  def test_batch_activate_atomicity_success(self) -> None:
    """Batch activation should succeed for non-conflicting targets."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-1",
          "title": "Target 1",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-2",
          "title": "Target 2",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["docs/**"],
          "parallel_mode": "safe",
        }),
      ]) + "\n",
    )
    write(self.root / ".agents/ideas/ideas.jsonl", "")
    
    proc = self.run_ideas("batch-activate", "--targets", "target-1,target-2", check=False)
    self.assertEqual(proc.returncode, 0)
    self.assertIn("Batch activation", proc.stdout)
    self.assertIn("target-1", proc.stdout)
    self.assertIn("target-2", proc.stdout)
    
    targets_rows = [json.loads(line) for line in (self.root / ".agents/targets/targets.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in targets_rows:
      if row["id"] in ["target-1", "target-2"]:
        self.assertIn("activated_at", row)
        self.assertIn("activated_by", row)

  def test_batch_activate_atomicity_failure_on_conflict(self) -> None:
    """Batch activation should fail atomically if write_scope conflicts detected."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-x",
          "title": "Target X",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/**"],
          "parallel_mode": "safe",
        }),
        json.dumps({
          "id": "target-y",
          "title": "Target Y",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["bootstrap/tools/**"],
          "parallel_mode": "safe",
        }),
      ]) + "\n",
    )
    
    proc = self.run_ideas("batch-activate", "--targets", "target-x,target-y", check=False)
    self.assertNotEqual(proc.returncode, 0)
    # Error message should be in stdout (printed before return)
    output = proc.stdout + proc.stderr
    self.assertIn("conflict", output.lower())
    
    targets_rows = [json.loads(line) for line in (self.root / ".agents/targets/targets.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in targets_rows:
      self.assertNotIn("activated_at", row)

  def test_batch_recommend_json_output(self) -> None:
    """Batch recommend should output valid JSON with --json flag."""
    write(
      self.root / ".agents/targets/targets.jsonl",
      "\n".join([
        json.dumps({
          "id": "target-p",
          "title": "Target P",
          "owner": "ideas",
          "status": "active",
          "write_scope": ["ideas/**"],
          "parallel_mode": "safe",
        }),
      ]) + "\n",
    )
    write(self.root / ".agents/ideas/ideas.jsonl", "")
    
    proc = self.run_ideas("batch", "--recommend", "--json")
    self.assertEqual(proc.returncode, 0)
    data = json.loads(proc.stdout)
    self.assertIn("batch_id", data)
    self.assertIn("targets", data)
    self.assertIn("total_targets", data)
    self.assertIn("conflicts_detected", data)

  def run_ideas(self, *args: str, check: bool = True) -> RunResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
      try:
        code = ideas.main(["--root", str(self.root), *args])
      except SystemExit as exc:
        if isinstance(exc.code, int):
          code = exc.code
        elif exc.code is None:
          code = 0
        else:
          code = 1
    result = RunResult(code, stdout.getvalue(), stderr.getvalue())
    if check and result.returncode != 0:
      raise AssertionError(f"Exit code {result.returncode}: {result.stderr}")
    return result


if __name__ == "__main__":
  unittest.main()
