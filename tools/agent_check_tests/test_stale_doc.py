from __future__ import annotations

import unittest

from tools.agent_check import stale_doc_issues

from tools.agent_check_tests._fixture import FixtureCase, write
import json


def _has(issues: list[str], needle: str) -> bool:
  return any(needle in issue for issue in issues)


class StaleDocTest(FixtureCase):
  def test_minimal_repo_is_clean(self) -> None:
    self.assertEqual(stale_doc_issues(self.root), [])

  def test_skill_md_without_agents_entry(self) -> None:
    write(
      self.root / ".agents/skills/orphan/SKILL.md",
      "---\nname: orphan\ndescription: x\n---\nbody\n",
    )
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "skill missing from AGENTS.md §2.1: .agents/skills/orphan"))

  def test_agents_lists_skill_with_no_skill_md(self) -> None:
    text = (self.root / "AGENTS.md").read_text()
    text = text.replace(
      "| `doc-sync` | always | `.agents/skills/doc-sync/SKILL.md` |",
      "| `doc-sync` | always | `.agents/skills/doc-sync/SKILL.md` |\n"
      "| `ghost` | x | `.agents/skills/ghost/SKILL.md` |",
    )
    (self.root / "AGENTS.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "AGENTS.md §2.1 lists skill `ghost`"))

  def test_index_references_unknown_skill(self) -> None:
    text = (self.root / ".agents/skills/index.md").read_text()
    text += "| `tools/foo` | `phantom` | nothing |\n"
    (self.root / ".agents/skills/index.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "references unknown skill `phantom`"))

  def test_skill_md_frontmatter_name_mismatch(self) -> None:
    skill = self.root / ".agents/skills/doc-sync/SKILL.md"
    skill.write_text("---\nname: not-doc-sync\ndescription: x\n---\nbody\n")
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "name 'not-doc-sync' != dir name 'doc-sync'"))

  def test_skill_md_missing_frontmatter(self) -> None:
    skill = self.root / ".agents/skills/doc-sync/SKILL.md"
    skill.write_text("body without frontmatter\n")
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "frontmatter malformed or missing"))

  def test_skill_md_missing_description(self) -> None:
    skill = self.root / ".agents/skills/doc-sync/SKILL.md"
    skill.write_text("---\nname: doc-sync\ndescription:\n---\nbody\n")
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "missing 'description'"))

  def test_tool_on_disk_missing_in_agents(self) -> None:
    new_tool = self.root / "tools/extra-tool"
    new_tool.write_text("#!/bin/sh\nexit 0\n")
    new_tool.chmod(0o755)
    facet_path = self.root / ".agents/facet/commands/facet.json"
    facet = json.loads(facet_path.read_text())
    facet["commands"].append({"name": "extra-tool", "purpose": "does extra"})
    facet_path.write_text(json.dumps(facet))
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "tool missing from AGENTS.md §8: tools/extra-tool"))

  def test_command_inventory_comes_from_facet(self) -> None:
    issues = stale_doc_issues(self.root)
    self.assertEqual(issues, [])

  def test_command_inventory_does_not_fall_back_to_repo_json(self) -> None:
    config = json.loads((self.root / ".agents/repo.json").read_text())
    config["commands"] = ["sample-tool"]
    (self.root / ".agents/repo.json").write_text(json.dumps(config))
    (self.root / ".agents/facet/commands/facet.json").unlink()
    issues = stale_doc_issues(self.root)
    self.assertTrue(
      _has(
        issues,
        "AGENTS.md §8 lists command `sample-tool` but .agents/facet/*/facet.json does not",
      )
    )

  def test_tool_in_agents_missing_on_disk(self) -> None:
    text = (self.root / "AGENTS.md").read_text()
    text = text.replace(
      "| `sample-tool` | — | does foo |",
      "| `sample-tool` | — | does foo |\n| `missing-tool` | — | gone |",
    )
    (self.root / "AGENTS.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "AGENTS.md §8 lists command `missing-tool`"))

  def test_subsystem_on_disk_missing_in_agents(self) -> None:
    write(self.root / "src/newmod/module.toml", "lib(name='newmod')\n")
    write(self.root / "src/newmod/AGENTS.md", "# newmod\n")
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "subsystem missing from AGENTS.md §15: src/newmod"))

  def test_subsystem_missing_nested_agents(self) -> None:
    write(self.root / "src/badmod/module.toml", "lib(name='badmod')\n")
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "subsystem missing nested AGENTS.md: src/badmod"))

  def test_subsystem_inventory_does_not_fall_back_to_default_glob(self) -> None:
    config = json.loads((self.root / ".agents/repo.json").read_text())
    config["facet_config"]["root"]["subsystem_descriptor_globs"] = []
    (self.root / ".agents/repo.json").write_text(json.dumps(config))
    write(self.root / "src/newmod/module.toml", "lib(name='newmod')\n")
    write(self.root / "src/newmod/AGENTS.md", "# newmod\n")
    issues = stale_doc_issues(self.root)
    self.assertFalse(_has(issues, "subsystem missing from AGENTS.md §15: src/newmod"))

  def test_subsystem_in_agents_missing_on_disk(self) -> None:
    text = (self.root / "AGENTS.md").read_text()
    text = text.replace(
      "| Subsystem | Layer | Purpose | Detail |\n|-----------|-------|---------|--------|",
      "| Subsystem | Layer | Purpose | Detail |\n|-----------|-------|---------|--------|\n"
      "| `src/ghost` | x | y | z |",
    )
    (self.root / "AGENTS.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "AGENTS.md §15 lists subsystem `src/ghost`"))

  def test_plan_referenced_but_missing(self) -> None:
    text = (self.root / "AGENTS.md").read_text()
    text += "\nSee `plans/missing.md` for context.\n"
    (self.root / "AGENTS.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "plan referenced but missing: plans/missing.md"))

  def test_plan_referenced_from_skill_must_exist(self) -> None:
    skill = self.root / ".agents/skills/doc-sync/SKILL.md"
    skill.write_text(
      "---\nname: doc-sync\ndescription: x\n---\nSee `plans/ghost.md`.\n"
    )
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "plan referenced but missing: plans/ghost.md"))

  def test_review_checklist_missing(self) -> None:
    text = (self.root / ".agents/skills/index.md").read_text()
    text += "| `tools/foo` | `doc-sync` | see `.agents/reviews/missing.md` |\n"
    (self.root / ".agents/skills/index.md").write_text(text)
    issues = stale_doc_issues(self.root)
    self.assertTrue(_has(issues, "review checklist referenced but missing: .agents/reviews/missing.md"))


if __name__ == "__main__":
  unittest.main()
