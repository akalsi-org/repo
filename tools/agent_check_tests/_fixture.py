"""Synthetic ROOT fixture used by agent_check tests.

Builds a minimal but consistent worktree (git-initialized, AGENTS.md +
skill index + one skill file + one tool + a § 5/§ 8/§ 15 scaffold) so each
test can mutate one piece and verify a single check fires.
"""
from __future__ import annotations

import atexit
import os
import shutil
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
  "facet_config": {
    "root": {
      "subsystem_descriptor_globs": ["src/*/module.toml"]
    },
    "git_hooks": {
      "vscode_extensions": []
    },
    "bootstrap": {
      "source_mirror_repo": null,
      "bootstrap_artifacts": []
    }
  }
}
"""


COMMANDS_FACET = """
{
  "name": "commands",
  "description": "Top-level commands",
  "owns": ["tools/**"],
  "commands": [
    {"name": "sample-tool", "purpose": "does foo"}
  ],
  "checks": [],
  "docs": []
}
"""


class TempRepo:
  """Creates a self-contained git repo for a single unittest case."""

  def __init__(self) -> None:
    self._td = tempfile.TemporaryDirectory()
    self.root = Path(self._td.name) / "repo"
    shutil.copytree(_seed_repo_root(), self.root)

  def cleanup(self) -> None:
    self._td.cleanup()


class FixtureCase(unittest.TestCase):
  """Mixin: each test gets a fresh `self.repo`."""

  def setUp(self) -> None:
    self.repo = TempRepo()
    self.root = self.repo.root

  def tearDown(self) -> None:
    self.repo.cleanup()


_SEED_TEMP: tempfile.TemporaryDirectory[str] | None = None
_SEED_ROOT: Path | None = None


def _seed_repo_root() -> Path:
  global _SEED_TEMP, _SEED_ROOT
  if _SEED_ROOT is not None:
    return _SEED_ROOT
  _SEED_TEMP = tempfile.TemporaryDirectory()
  _SEED_ROOT = Path(_SEED_TEMP.name) / "seed"
  write(_SEED_ROOT / "AGENTS.md", AGENTS_MD)
  write(_SEED_ROOT / ".agents/repo.json", REPO_JSON)
  write(_SEED_ROOT / ".agents/facet/commands/facet.json", COMMANDS_FACET)
  write(_SEED_ROOT / ".agents/skills/index.md", SKILL_INDEX)
  write(_SEED_ROOT / ".agents/skills/doc-sync/SKILL.md", DOC_SYNC_SKILL)
  write(_SEED_ROOT / "tools/sample-tool", "#!/bin/sh\nexit 0\n")
  (_SEED_ROOT / "tools/sample-tool").chmod(0o755)
  _git(["init", "-q", "-b", "main"], _SEED_ROOT)
  _git(["add", "-A"], _SEED_ROOT)
  _git(["commit", "-q", "-m", "init"], _SEED_ROOT)
  atexit.register(_cleanup_seed_repo)
  return _SEED_ROOT


def _cleanup_seed_repo() -> None:
  global _SEED_TEMP, _SEED_ROOT
  if _SEED_TEMP is not None:
    _SEED_TEMP.cleanup()
  _SEED_TEMP = None
  _SEED_ROOT = None
