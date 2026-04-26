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
      "--state",
      "shaped",
    )
    proc = self.run_ideas("ready")
    self.assertIn("ready: Ready idea", proc.stdout)

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
