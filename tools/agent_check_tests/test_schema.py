from __future__ import annotations

import json
import unittest

from tools.agent_check import schema_issues, stale_doc_issues
from tools.agent_check_tests._fixture import FixtureCase


def _has(issues: list[str], needle: str) -> bool:
  return any(needle in issue for issue in issues)


class SchemaTest(FixtureCase):
  def test_minimal_repo_schema_is_clean(self) -> None:
    self.assertEqual(schema_issues(self.root), [])

  def test_missing_schema_file_is_stale_doc_issue(self) -> None:
    (self.root / "schemas/idea.schema.json").unlink()
    self.assertTrue(_has(stale_doc_issues(self.root) + schema_issues(self.root), "idea.schema.json"))

  def test_facet_manifest_requires_owns_array(self) -> None:
    facet_path = self.root / ".agents/facet/commands/facet.json"
    facet = json.loads(facet_path.read_text(encoding="utf-8"))
    facet["owns"] = "tools/**"
    facet_path.write_text(json.dumps(facet), encoding="utf-8")
    self.assertTrue(_has(schema_issues(self.root), "owns must be non-empty string array"))

  def test_idea_rows_require_target(self) -> None:
    idea_path = self.root / ".agents/ideas/ideas.jsonl"
    idea_path.write_text(
      json.dumps({"id": "x", "title": "X", "owner": "commands", "state": "shaped"}),
      encoding="utf-8",
    )
    self.assertTrue(_has(schema_issues(self.root), "target must be non-empty string"))


if __name__ == "__main__":
  unittest.main()
