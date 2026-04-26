from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def spec(path: Path, name: str, deps: list[str] | None = None) -> None:
  dep_words = " ".join(deps or [])
  write(
    path,
    f"""
    TOOL_NAME={name}
    TOOL_VERSION=1
    TOOL_DEPS=({dep_words})
    if [[ "${{BOOTSTRAP_PLAN_ONLY:-0}}" == 1 ]]; then
      return 0 2>/dev/null || exit 0
    fi
    """,
  )


class BootstrapPlanTest(unittest.TestCase):
  def setUp(self) -> None:
    self._td = tempfile.TemporaryDirectory()
    self.root = Path(self._td.name)
    shutil.copy2(ROOT / "repo.sh", self.root / "repo.sh")
    (self.root / "repo.sh").chmod(0o755)
    (self.root / "bootstrap" / "tools").mkdir(parents=True)
    self.local = self.root / ".local-test"

  def tearDown(self) -> None:
    self._td.cleanup()

  def run_plan(self, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REPO_LOCAL"] = str(self.local)
    return subprocess.run(
      [str(self.root / "repo.sh"), "__repo_bootstrap_plan", *args],
      cwd=self.root,
      env=env,
      text=True,
      capture_output=True,
      check=False,
    )

  def assert_plan_error(self, expected: str) -> None:
    result = self.run_plan()
    self.assertNotEqual(result.returncode, 0, result.stdout)
    self.assertIn(expected, result.stderr)

  def test_valid_dependency_graph_is_batched_when_deps_are_ready(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "a")
    spec(self.root / "bootstrap/tools/b.sh", "b", ["a"])
    spec(self.root / "bootstrap/tools/c.sh", "c", ["a"])
    spec(self.root / "bootstrap/tools/d.sh", "d", ["b", "c"])

    result = self.run_plan()

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(
      result.stdout,
      "batch 0: a\n"
      "batch 1: b c\n"
      "batch 2: d\n",
    )
    self.assertEqual(result.stderr, "")

  def test_json_plan_includes_tools_specs_deps_and_ready_batches(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "a")
    spec(self.root / "bootstrap/tools/b.sh", "b", ["a"])
    spec(self.root / "bootstrap/tools/c.sh", "c", ["a"])
    spec(self.root / "bootstrap/tools/d.sh", "d", ["b", "c"])

    result = self.run_plan("--json")

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stderr, "")
    self.assertEqual(
      json.loads(result.stdout),
      {
        "tools": [
          {
            "name": "a",
            "deps": [],
            "spec_path": str(self.root / "bootstrap/tools/a.sh"),
          },
          {
            "name": "b",
            "deps": ["a"],
            "spec_path": str(self.root / "bootstrap/tools/b.sh"),
          },
          {
            "name": "c",
            "deps": ["a"],
            "spec_path": str(self.root / "bootstrap/tools/c.sh"),
          },
          {
            "name": "d",
            "deps": ["b", "c"],
            "spec_path": str(self.root / "bootstrap/tools/d.sh"),
          },
        ],
        "ready_batches": [["a"], ["b", "c"], ["d"]],
      },
    )

  def test_plan_rejects_unknown_arguments(self) -> None:
    result = self.run_plan("--yaml")

    self.assertNotEqual(result.returncode, 0, result.stdout)
    self.assertIn(
      "usage: ./repo.sh __repo_bootstrap_plan [--json]",
      result.stderr,
    )

  def test_unknown_dependency_is_rejected(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "a", ["missing"])

    self.assert_plan_error("bootstrap tool a depends on unknown tool missing")

  def test_self_dependency_is_rejected(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "a", ["a"])

    self.assert_plan_error("bootstrap tool a depends on itself")

  def test_duplicate_tool_name_is_rejected(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "dup")
    spec(self.root / "bootstrap/tools/b.sh", "dup")

    self.assert_plan_error("duplicate bootstrap TOOL_NAME dup")

  def test_cycle_is_rejected(self) -> None:
    spec(self.root / "bootstrap/tools/a.sh", "a", ["b"])
    spec(self.root / "bootstrap/tools/b.sh", "b", ["a"])

    self.assert_plan_error("bootstrap dependency cycle among:")

  def test_plan_only_query_does_not_source_fetch_helper(self) -> None:
    sentinel = self.root / "helper-ran"
    write(
      self.root / "bootstrap/fetch_fake.sh",
      f"""
      printf ran > {sentinel}
      exit 42
      """,
    )
    write(
      self.root / "bootstrap/tools/a.sh",
      """
      TOOL_NAME=a
      TOOL_VERSION=1
      TOOL_DEPS=()
      if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
        return 0 2>/dev/null || exit 0
      fi
      . "$REPO_ROOT/bootstrap/fetch_fake.sh"
      """,
    )

    result = self.run_plan()

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, "batch 0: a\n")
    self.assertFalse(sentinel.exists())

  def test_plan_does_not_fall_back_to_repo_config_tool_list(self) -> None:
    write(
      self.root / ".agents/repo.json",
      """
      {
        "bootstrap": {
          "tools": ["ghost"]
        }
      }
      """,
    )

    result = self.run_plan()

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, "")
    self.assertEqual(result.stderr, "")


if __name__ == "__main__":
  unittest.main()
