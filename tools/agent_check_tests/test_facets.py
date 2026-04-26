from __future__ import annotations

import unittest

from tools.agent_check import build_report
from tools.facets import command_names, load_facets, owner_names

from tools.agent_check_tests._fixture import FixtureCase, write


class FacetsTest(FixtureCase):
  def test_root_facet_uses_slash_display_name(self) -> None:
    write(
      self.root / ".agents/facet/root/facet.json",
      """
      {
        "name": "/",
        "description": "Root substrate",
        "owns": ["AGENTS.md"],
        "consider": [],
        "commands": [],
        "checks": [],
        "docs": []
      }
      """,
    )
    facets = {facet.key: facet for facet in load_facets(self.root)}
    self.assertEqual(facets["root"].name, "/")

  def test_non_root_facet_name_must_match_directory(self) -> None:
    write(
      self.root / ".agents/facet/commands/facet.json",
      """
      {
        "name": "not-commands",
        "description": "bad",
        "owns": [],
        "commands": [],
        "checks": [],
        "docs": []
      }
      """,
    )
    with self.assertRaisesRegex(ValueError, "must match facet directory"):
      load_facets(self.root)

  def test_command_inventory_is_merged_from_all_facets(self) -> None:
    write(
      self.root / ".agents/facet/kb/facet.json",
      """
      {
        "name": "kb",
        "description": "KB",
        "owns": ["tools/agent"],
        "commands": [
          {"name": "agent", "purpose": "query KB"}
        ],
        "checks": [],
        "docs": []
      }
      """,
    )
    self.assertEqual(command_names(self.root), ["agent", "sample-tool"])

  def test_owner_facet_closeout_checks_enter_report(self) -> None:
    write(
      self.root / ".agents/facet/docs/facet.json",
      """
      {
        "name": "docs",
        "description": "docs",
        "owns": ["docs/**"],
        "commands": [],
        "checks": [
          {"name": "docs_check", "command": "./repo.sh docs_check", "closeout": true}
        ],
        "docs": []
      }
      """,
    )
    write(self.root / "docs/example.md", "# example\n")
    report = build_report(self.root)
    self.assertIn("./repo.sh docs_check", report.closeout)

  def test_considerations_are_notes_not_closeout_checks(self) -> None:
    write(
      self.root / ".agents/facet/docs/facet.json",
      """
      {
        "name": "docs",
        "description": "docs",
        "owns": ["docs/**"],
        "consider": [
          {
            "paths": ["tools/agent_check.py"],
            "reason": "May affect doc validation.",
            "checks": ["./repo.sh should_not_run"]
          }
        ],
        "commands": [],
        "checks": [],
        "docs": []
      }
      """,
    )
    write(self.root / "tools/agent_check.py", "# changed\n")
    report = build_report(self.root)
    self.assertIn("consider `docs`: May affect doc validation.", report.notes)
    self.assertNotIn("./repo.sh should_not_run", report.closeout)

  def test_changed_path_with_no_owner_is_reported(self) -> None:
    write(self.root / "unowned.txt", "orphan\n")
    report = build_report(self.root)
    self.assertIn(
      "facet ownership missing for changed path `unowned.txt`: "
      "zero owner facets",
      report.ownership,
    )

  def test_changed_path_with_multiple_owners_is_reported(self) -> None:
    write(
      self.root / ".agents/facet/docs/facet.json",
      """
      {
        "name": "docs",
        "description": "docs",
        "owns": [
          ".agents/facet/docs/**",
          "tools/agent_check.py"
        ],
        "commands": [],
        "checks": [],
        "docs": []
      }
      """,
    )
    write(self.root / "tools/agent_check.py", "# changed\n")
    report = build_report(self.root)
    self.assertIn(
      "facet ownership conflict for changed path `tools/agent_check.py`: "
      "multiple owner facets (`commands`, `docs`)",
      report.ownership,
    )

  def test_consideration_does_not_count_as_owner(self) -> None:
    write(
      self.root / ".agents/facet/docs/facet.json",
      """
      {
        "name": "docs",
        "description": "docs",
        "owns": [".agents/facet/docs/**"],
        "consider": [
          {
            "paths": ["unowned.txt"],
            "reason": "May affect docs."
          }
        ],
        "commands": [],
        "checks": [],
        "docs": []
      }
      """,
    )
    write(self.root / "unowned.txt", "orphan\n")
    report = build_report(self.root)
    self.assertEqual(owner_names(self.root, "unowned.txt"), [])
    self.assertIn("consider `docs`: May affect docs.", report.notes)
    self.assertIn(
      "facet ownership missing for changed path `unowned.txt`: "
      "zero owner facets",
      report.ownership,
    )


if __name__ == "__main__":
  unittest.main()
