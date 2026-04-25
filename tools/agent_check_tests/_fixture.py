"""Synthetic ROOT fixture used by agent-check tests.

Builds a minimal but consistent worktree (git-initialized, AGENTS.md +
skill index + one skill file + one tool + a § 5/§ 8/§ 15 scaffold) so each
test can mutate one piece and verify a single check fires.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


def _git(args: list[str], cwd: Path) -> None:
  env = os.environ.copy()
  env["GIT_AUTHOR_NAME"] = "t"
  env["GIT_AUTHOR_EMAIL"] = "t@example.invalid"
  env["GIT_COMMITTER_NAME"] = "t"
  env["GIT_COMMITTER_EMAIL"] = "t@example.invalid"
  subprocess.run(
    ["git", *args],
    cwd=cwd,
    check=True,
    capture_output=True,
    env=env,
  )


def write(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


AGENTS_MD = """
# AGENTS.md

## 2.1 Agent skills

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `doc-sync` | always | `.agents/skills/doc-sync/SKILL.md` |

## 5. Repo layout

- `.agents/skills/index.md`
- `tools/`

## 8. Commands

| Command | Mode | Purpose |
|---------|------|---------|
| `sample-tool` | — | does foo |

## 15. Subsystems

| Subsystem | Layer | Purpose | Detail |
|-----------|-------|---------|--------|

## 16. Decisions
end
"""


SKILL_INDEX = """
# Skill Routing Index

| Path pattern | Skills | Docs / review notes |
|--------------|--------|---------------------|
| `src/**/*.c`, `src/**/*.h` | `doc-sync` | Run `./repo.sh lint`. |
"""


DOC_SYNC_SKILL = """
---
name: doc-sync
description: keep docs current
---
body
"""


REPO_JSON = """
{
  "commands": ["sample-tool"],
  "command_table": "AGENTS.md",
  "subsystem_descriptor_globs": ["src/*/module.toml"],
  "source_mirror_repo": null,
  "bootstrap_artifacts": []
}
"""


class TempRepo:
  """Creates a self-contained git repo for a single unittest case."""

  def __init__(self) -> None:
    self._td = tempfile.TemporaryDirectory()
    self.root = Path(self._td.name)
    self._init_minimal()

  def _init_minimal(self) -> None:
    write(self.root / "AGENTS.md", AGENTS_MD)
    write(self.root / ".agents/repo.json", REPO_JSON)
    write(self.root / ".agents/skills/index.md", SKILL_INDEX)
    write(self.root / ".agents/skills/doc-sync/SKILL.md", DOC_SYNC_SKILL)
    write(self.root / "tools/sample-tool", "#!/bin/sh\nexit 0\n")
    (self.root / "tools/sample-tool").chmod(0o755)
    _git(["init", "-q", "-b", "main"], self.root)
    _git(["add", "-A"], self.root)
    _git(["commit", "-q", "-m", "init"], self.root)

  def cleanup(self) -> None:
    self._td.cleanup()


class FixtureCase(unittest.TestCase):
  """Mixin: each test gets a fresh `self.repo`."""

  def setUp(self) -> None:
    self.repo = TempRepo()
    self.root = self.repo.root

  def tearDown(self) -> None:
    self.repo.cleanup()
