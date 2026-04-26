from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.targets import TARGETS_REL, load_target_ledger


def write(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")


class TargetsTest(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    write(
      self.root / ".agents/facet/ideas/facet.json",
      json.dumps(
        {
          "name": "ideas",
          "description": "Idea inventory",
          "owns": [".agents/ideas/**", ".agents/targets/**"],
          "commands": [],
          "checks": [],
          "docs": [],
        }
      ),
    )

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_loads_targets_and_validates_ref(self) -> None:
    write(
      self.root / TARGETS_REL,
      json.dumps(
        {
          "id": "target-ledger",
          "title": "Target ledger",
          "owner": "ideas",
          "status": "active",
          "review_cadence": "monthly",
          "check": "./repo.sh ideas report --cost",
        }
      ) + "\n",
    )

    ledger = load_target_ledger(self.root)

    self.assertEqual(list(ledger), ["target-ledger"])
    self.assertEqual(ledger.require("target-ledger").title, "Target ledger")
    self.assertEqual(ledger.validate_ref("target-ledger"), [])
    self.assertEqual(
      ledger.validate_ref("missing", idea_id="idea-1"),
      ["idea-1: unknown target `missing`"],
    )

  def test_duplicate_target_id_fails_loudly(self) -> None:
    write(
      self.root / TARGETS_REL,
      "\n".join([
        json.dumps({"id": "dup", "title": "One", "owner": "ideas", "status": "active"}),
        json.dumps({"id": "dup", "title": "Two", "owner": "ideas", "status": "active"}),
      ]) + "\n",
    )

    with self.assertRaisesRegex(ValueError, "duplicate target id `dup`"):
      load_target_ledger(self.root)

  def test_missing_ledger_fails_loudly(self) -> None:
    with self.assertRaisesRegex(ValueError, f"{TARGETS_REL} missing"):
      load_target_ledger(self.root)


if __name__ == "__main__":
  unittest.main()
