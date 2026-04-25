from __future__ import annotations

import contextlib
import io
import json
import unittest

from tools.agent_kb import (
  action_table,
  main,
  probe,
  query_backlog,
  query_feedback_summary,
  query_recommend_tools,
  query_request_brief,
  query_think,
  query_table,
  rebuild_cache,
  read_fact,
  stale_issues,
)

from tools.agent_kb_tests._fixture import TempRepo, write


class AgentKbTest(unittest.TestCase):
  def setUp(self) -> None:
    self.repo = TempRepo()
    self.root = self.repo.root

  def tearDown(self) -> None:
    self.repo.cleanup()

  def test_probe_rebuilds_and_matches(self) -> None:
    result = probe(self.root, paths=["tools/sample-tool"], verb="change")
    self.assertEqual(list(result.skills), ["build-commands"])
    self.assertEqual([fact.id for fact in result.facts], ["build-fact"])

  def test_rebuild_reuses_unchanged_sources(self) -> None:
    first = rebuild_cache(self.root)
    second = rebuild_cache(self.root)
    self.assertEqual(first["rebuilt_sources"], first["sources"])
    self.assertEqual(second["rebuilt_sources"], 0)
    self.assertEqual(second["reused_sources"], second["sources"])

  def test_read_fact_returns_fact_payload(self) -> None:
    rebuild_cache(self.root)
    fact = read_fact("src-fact", self.root)
    self.assertEqual(fact.refs, ("src/example/AGENTS.md",))
    self.assertEqual(fact.says, ("Read nested subsystem AGENTS.",))

  def test_stale_reports_invalid_ref(self) -> None:
    write(
      self.root / ".agents/kb-src/bad.jsonl",
      """
      {"id":"bad-ref","says":["oops"],"refs":["missing.md"]}
      """,
    )
    issues = stale_issues(self.root)
    self.assertTrue(any("ref path missing: missing.md" in issue for issue in issues))

  def test_cli_json_output(self) -> None:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      rc = main(
        [
          "--root",
          str(self.root),
          "--query",
          "probe",
          "--path",
          "tools/sample-tool",
          "--verb",
          "change",
          "--json",
        ]
      )
    self.assertEqual(rc, 0)
    payload = json.loads(buf.getvalue())
    self.assertEqual(payload["skills"], ["build-commands"])
    self.assertEqual(payload["facts"][0]["id"], "build-fact")

  def test_action_insert_and_query_table(self) -> None:
    action_table(
      self.root,
      "requests",
      "insert",
      fields={
        "id": "req-1",
        "path": "tools/sample-tool",
        "verb": "change",
        "phase": "implement",
      },
    )
    payload = query_table(self.root, "requests", filters={"id": "req-1"})
    self.assertEqual(payload["row_count"], 1)
    self.assertEqual(payload["rows"][0]["path"], "tools/sample-tool")

  def test_request_brief_joins_request_to_facts(self) -> None:
    action_table(
      self.root,
      "requests",
      "insert",
      fields={
        "id": "req-2",
        "path": "tools/sample-tool",
        "verb": "change",
        "phase": "implement",
        "claims": ["build-commands"],
      },
    )
    payload = query_request_brief(self.root, "req-2")
    briefing = payload["briefing"]
    self.assertEqual(briefing["skills"], ["build-commands"])
    self.assertEqual(briefing["missing_skills"], [])
    self.assertEqual(briefing["facts"][0]["id"], "build-fact")

  def test_source_table_query_reads_cached_rows(self) -> None:
    payload = query_table(self.root, "tool_catalog")
    self.assertEqual(payload["row_count"], 4)
    self.assertEqual(payload["rows"][0]["table"], "tool_catalog")

  def test_backlog_query_filters_and_formats(self) -> None:
    payload = query_backlog(self.root, area="runtime-perf", priority="P1")
    self.assertEqual(payload["row_count"], 1)
    self.assertEqual(payload["rows"][0]["id"], "bp1")

  def test_recommend_tools_from_backlog_problem(self) -> None:
    payload = query_recommend_tools(self.root, problem_id="bp1")
    tool_ids = [row["id"] for row in payload["tools"]]
    self.assertEqual(tool_ids, ["bench", "source-scan", "test"])

  def test_feedback_summary_joins_solver_runs_and_tools(self) -> None:
    action_table(
      self.root,
      "solver_runs",
      "insert",
      fields={
        "id": "run-1",
        "goal": "tighten runtime recommendations",
        "area": "runtime-perf",
        "priority": "P1",
        "path": "tools/sample-tool",
        "problem_id": "bp1",
      },
    )
    for row in (
      {
        "id": "tf-source",
        "run_id": "run-1",
        "tool_id": "source-scan",
        "used": True,
        "usefulness": 2,
        "outcome": "high-value",
      },
      {
        "id": "tf-bench",
        "run_id": "run-1",
        "tool_id": "bench",
        "used": False,
        "usefulness": -1,
        "outcome": "recommended-not-used",
      },
    ):
      action_table(self.root, "tool_feedback", "insert", fields=row)
    payload = query_feedback_summary(self.root, problem_id="bp1")
    self.assertEqual(payload["row_count"], 2)
    self.assertEqual(payload["rows"][0]["solver_run"]["goal"], "tighten runtime recommendations")
    self.assertEqual(payload["tools"][0]["tool_id"], "source-scan")
    self.assertEqual(payload["tools"][1]["tool_id"], "bench")

  def test_recommend_tools_uses_feedback_history_and_feedback_only_tools(self) -> None:
    action_table(
      self.root,
      "solver_runs",
      "insert",
      fields={
        "id": "run-2",
        "area": "runtime-perf",
        "priority": "P1",
        "path": "tools/sample-tool",
        "problem_id": "bp1",
      },
    )
    for row in (
      {
        "id": "tf-source-2",
        "run_id": "run-2",
        "tool_id": "source-scan",
        "used": True,
        "usefulness": 3,
        "outcome": "high-value",
      },
      {
        "id": "tf-test-2",
        "run_id": "run-2",
        "tool_id": "test",
        "used": True,
        "usefulness": 2,
        "outcome": "helpful",
      },
      {
        "id": "tf-bench-2",
        "run_id": "run-2",
        "tool_id": "bench",
        "used": False,
        "usefulness": -1,
        "outcome": "recommended-not-used",
      },
      {
        "id": "tf-lint-2",
        "run_id": "run-2",
        "tool_id": "lint",
        "used": True,
        "usefulness": 1,
        "outcome": "helpful",
      },
    ):
      action_table(self.root, "tool_feedback", "insert", fields=row)
    payload = query_recommend_tools(self.root, problem_id="bp1")
    tool_ids = [row["id"] for row in payload["tools"]]
    self.assertEqual(tool_ids[:4], ["source-scan", "test", "lint", "bench"])
    self.assertIn("feedback", payload)
    self.assertEqual(payload["tools"][0]["feedback"]["positive_count"], 1)
    self.assertEqual(payload["tools"][-1]["feedback"]["unused_count"], 1)

  def test_think_synthesizes_fact_backlog_and_tools(self) -> None:
    action_table(
      self.root,
      "requests",
      "insert",
      fields={
        "id": "req-think",
        "path": "tools/sample-tool",
        "verb": "change",
      },
    )
    payload = query_think(
      self.root,
      subjects=["runtime-perf"],
      verbs=["optimize"],
      objects=["tools/sample-tool"],
      limit=8,
    )
    kinds = [row["kind"] for row in payload["results"]]
    self.assertIn("backlog", kinds)
    self.assertIn("tool", kinds)
    self.assertIn("fact", kinds)

  def test_cli_think_json_output(self) -> None:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      rc = main(
        [
          "--root",
          str(self.root),
          "query",
          "think",
          "--subject",
          "runtime-perf",
          "--object",
          "tools/sample-tool",
          "--json",
        ]
      )
    self.assertEqual(rc, 0)
    payload = json.loads(buf.getvalue())
    self.assertTrue(payload["results"])
    self.assertIn("tags", payload["results"][0])

  def test_cli_feedback_summary_json_output(self) -> None:
    action_table(
      self.root,
      "solver_runs",
      "insert",
      fields={
        "id": "run-cli",
        "area": "runtime-perf",
        "priority": "P1",
        "path": "tools/sample-tool",
      },
    )
    action_table(
      self.root,
      "tool_feedback",
      "insert",
      fields={
        "id": "tf-cli",
        "run_id": "run-cli",
        "tool_id": "source-scan",
        "used": True,
        "usefulness": 2,
      },
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      rc = main(
        [
          "--root",
          str(self.root),
          "query",
          "feedback-summary",
          "--area",
          "runtime-perf",
          "--path",
          "tools/sample-tool",
          "--json",
        ]
      )
    self.assertEqual(rc, 0)
    payload = json.loads(buf.getvalue())
    self.assertEqual(payload["tools"][0]["tool_id"], "source-scan")


if __name__ == "__main__":
  unittest.main()
