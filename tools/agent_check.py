"""agent_check core.

Importable module that drives `tools/agent_check`. Splitting the body
out lets `tools/agent_check_tests/` exercise individual checks against
synthetic ROOT trees instead of the live worktree.

Public surface:

- ``changed_paths(root)`` — modified + untracked file list, with untracked
  directory entries expanded to their actual files so route matching sees
  them.
- ``glob_match(path, pattern)`` — segment-based glob with recursive ``**``
  semantics (the stdlib ``pathlib.PurePath.match`` does not recurse on
  Python 3.10).
- ``parse_routes(root)`` — parses ``.agents/skills/index.md`` rows into
  ``{patterns, skills, note}`` records.
- ``route_advice(root, paths)`` — applies routes to a path list and returns
  ``(skills, notes, closeout_checks)``.
- ``stale_doc_issues(root)`` — bidirectional checks across AGENTS.md,
  SKILL.md frontmatter, the skill index, the tool/subsystem inventory, and
  any plan-file references.
- ``build_report`` / ``render_report`` / ``main`` — CLI assembly.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass


SKILL_INDEX_REL = ".agents/skills/index.md"
SKILLS_DIR_REL = ".agents/skills"
AGENTS_REL = "AGENTS.md"
REPO_CONFIG_REL = ".agents/repo.json"


@dataclass
class Report:
  paths: list[str]
  skills: list[str]
  notes: list[str]
  closeout: list[str]
  stale: list[str]

  @property
  def is_clean(self) -> bool:
    return not self.stale


# ---- changed paths ---------------------------------------------------------


def _run_git(
    root: pathlib.Path, args: list[str]
) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", *args],
    cwd=root,
    check=False,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )


def _expand_untracked_dir(root: pathlib.Path, rel_dir: str) -> list[str]:
  proc = _run_git(
    root,
    ["ls-files", "--others", "--exclude-standard", "-z", "--", rel_dir],
  )
  if proc.returncode == 0 and proc.stdout:
    return [c for c in proc.stdout.split("\0") if c]
  abs_dir = root / rel_dir
  if not abs_dir.is_dir():
    return [rel_dir]
  out: list[str] = []
  for child in abs_dir.rglob("*"):
    if child.is_file():
      out.append(child.relative_to(root).as_posix())
  return sorted(out)


def changed_paths(root: pathlib.Path) -> list[str]:
  proc = _run_git(root, ["status", "--porcelain=v1", "-z"])
  if proc.returncode != 0:
    return []

  paths: list[str] = []
  chunks = proc.stdout.split("\0")
  i = 0
  while i < len(chunks):
    entry = chunks[i]
    i += 1
    if not entry:
      continue
    if len(entry) < 4:
      continue
    status = entry[:2]
    path = entry[3:]
    if status[0] in {"R", "C"} and i < len(chunks):
      path = chunks[i]
      i += 1
    if path.endswith("/"):
      paths.extend(_expand_untracked_dir(root, path.rstrip("/")))
    else:
      paths.append(path)
  return sorted(set(paths))


# ---- glob matching ---------------------------------------------------------


def _match_segments(parts: list[str], pat_parts: list[str]) -> bool:
  if not pat_parts:
    return not parts
  head, *rest = pat_parts
  if head == "**":
    if _match_segments(parts, rest):
      return True
    if parts and _match_segments(parts[1:], pat_parts):
      return True
    return False
  if not parts:
    return False
  if fnmatch.fnmatchcase(parts[0], head):
    return _match_segments(parts[1:], rest)
  return False


def glob_match(path: str, pattern: str) -> bool:
  if path == pattern:
    return True
  return _match_segments(path.split("/"), pattern.split("/"))


# ---- skill index parsing ---------------------------------------------------


def _split_cell(cell: str) -> list[str]:
  return re.findall(r"`([^`]+)`", cell)


def parse_routes(root: pathlib.Path) -> list[dict[str, list[str] | str]]:
  index_path = root / SKILL_INDEX_REL
  if not index_path.exists():
    return []
  routes: list[dict[str, list[str] | str]] = []
  for line in index_path.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s.startswith("| `"):
      continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) != 3:
      continue
    routes.append(
      {
        "patterns": _split_cell(cells[0]),
        "skills": _split_cell(cells[1]),
        "note": cells[2],
      }
    )
  return routes


def route_advice(
    root: pathlib.Path, paths: list[str]
) -> tuple[set[str], list[str], set[str]]:
  skills: set[str] = set()
  notes: list[str] = []
  checks: set[str] = set()

  for route in parse_routes(root):
    patterns = route["patterns"]
    if not isinstance(patterns, list):
      continue
    if not any(glob_match(p, pat) for p in paths for pat in patterns):
      continue
    if isinstance(route["skills"], list):
      skills.update(route["skills"])
    note = route["note"]
    if isinstance(note, str):
      notes.append(note)
      for check in re.findall(
        r"`(\./repo\.sh [^`]+|git diff --check)`", note
      ):
        if "<" not in check and ">" not in check:
          checks.add(check)

  return skills, notes, checks


# ---- stale-doc detection ---------------------------------------------------


def _read(path: pathlib.Path) -> str:
  return path.read_text(encoding="utf-8") if path.exists() else ""


def _section(text: str, header_re: str) -> str:
  parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
  for part in parts:
    if re.match(header_re, part):
      return part
  return ""


def _frontmatter(text: str) -> dict[str, str] | None:
  if not text.startswith("---\n"):
    return None
  m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
  if not m:
    return None
  fm: dict[str, str] = {}
  for line in m.group(1).splitlines():
    if ":" in line:
      key, _, val = line.partition(":")
      fm[key.strip()] = val.strip()
  return fm


def _repo_config(root: pathlib.Path) -> dict[str, object]:
  path = root / REPO_CONFIG_REL
  if not path.exists():
    return {}
  raw = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(raw, dict):
    raise ValueError(f"{REPO_CONFIG_REL} must contain a JSON object")
  return raw


def _str_list(raw: object, *, field: str) -> list[str]:
  if raw is None:
    return []
  if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
    raise ValueError(f"{REPO_CONFIG_REL}:{field} must be list[str]")
  return list(raw)


def stale_doc_issues(root: pathlib.Path) -> list[str]:
  issues: list[str] = []
  config = _repo_config(root)
  agents = _read(root / AGENTS_REL)
  index_text = _read(root / SKILL_INDEX_REL)

  skill_files = sorted((root / SKILLS_DIR_REL).glob("*/SKILL.md"))
  skill_names_on_disk = {s.parent.name for s in skill_files}

  for skill in skill_files:
    rel_skill = skill.relative_to(root).as_posix()
    name = skill.parent.name
    if f"`{name}`" not in agents:
      issues.append(f"skill missing from AGENTS.md §2.1: {rel_skill}")
    fm = _frontmatter(_read(skill))
    if fm is None:
      issues.append(
        f"SKILL.md frontmatter malformed or missing: {rel_skill}"
      )
      continue
    if "name" not in fm:
      issues.append(f"SKILL.md missing 'name' in frontmatter: {rel_skill}")
    elif fm["name"] != name:
      issues.append(
        f"SKILL.md name '{fm['name']}' != dir name '{name}': {rel_skill}"
      )
    if not fm.get("description"):
      issues.append(
        f"SKILL.md missing 'description' in frontmatter: {rel_skill}"
      )

  section_2_1 = _section(agents, r"## 2\.1")
  for sn in re.findall(
    r"^\| `([a-z][a-z0-9_-]*)`\s*\|", section_2_1, re.MULTILINE
  ):
    if sn not in skill_names_on_disk:
      issues.append(
        f"AGENTS.md §2.1 lists skill `{sn}` but no SKILL.md exists"
      )

  for route in parse_routes(root):
    skills_cell = route.get("skills")
    if not isinstance(skills_cell, list):
      continue
    for sn in skills_cell:
      if sn and sn not in skill_names_on_disk:
        issues.append(
          f".agents/skills/index.md references unknown skill `{sn}`"
        )

  for command in sorted(_str_list(config.get("commands"), field="commands")):
    tool = root / "tools" / command
    if not tool.is_file():
      issues.append(
        f"{REPO_CONFIG_REL} lists command `{command}` but tools/{command} not found"
      )
      continue
    if f"`{command}`" not in agents:
      issues.append(f"tool missing from AGENTS.md §8: tools/{command}")

  section_8 = _section(agents, r"## 8\.")
  for tn in sorted(set(re.findall(r"`([a-z][a-z0-9_-]*)`", section_8))):
    if tn not in _str_list(config.get("commands"), field="commands"):
      issues.append(
        f"AGENTS.md §8 lists command `{tn}` but {REPO_CONFIG_REL} does not"
      )

  descriptor_globs = _str_list(
    config.get("subsystem_descriptor_globs"),
    field="subsystem_descriptor_globs",
  )
  for pattern in descriptor_globs:
    for descriptor in sorted(root.glob(pattern)):
      if not descriptor.is_file():
        continue
      rel_mod = descriptor.parent.relative_to(root).as_posix()
      if f"`{rel_mod}`" not in agents:
        issues.append(f"subsystem missing from AGENTS.md §15: {rel_mod}")
      if not (descriptor.parent / "AGENTS.md").exists():
        issues.append(f"subsystem missing nested AGENTS.md: {rel_mod}")

  section_15 = _section(agents, r"## 15\.")
  for sn in sorted(set(re.findall(r"`(src/[a-z][a-z0-9_-]*)`", section_15))):
    if not any(
        descriptor.parent.relative_to(root).as_posix() == sn
        for pattern in descriptor_globs
        for descriptor in root.glob(pattern)
        if descriptor.is_file()
    ):
      issues.append(
        f"AGENTS.md §15 lists subsystem `{sn}` but no configured descriptor found"
      )

  if (root / SKILL_INDEX_REL).exists() and (
    "`.agents/skills/index.md`" not in agents
  ):
    issues.append("skill index exists but is not referenced from AGENTS.md")

  for review in sorted(
    set(re.findall(r"`(\.agents/reviews/[^`]+\.md)`", index_text))
  ):
    if not (root / review).exists():
      issues.append(f"review checklist referenced but missing: {review}")

  plan_refs: set[str] = set(re.findall(r"`(plans/[^`]+\.md)`", agents))
  plan_refs.update(re.findall(r"`(plans/[^`]+\.md)`", index_text))
  for skill_md in skill_files:
    plan_refs.update(
      re.findall(r"`(plans/[^`]+\.md)`", _read(skill_md))
    )
  for ref in sorted(plan_refs):
    if not (root / ref).is_file():
      issues.append(f"plan referenced but missing: {ref}")

  return issues


# ---- report assembly + CLI -------------------------------------------------


def build_report(root: pathlib.Path) -> Report:
  paths = changed_paths(root)
  skills, notes, checks = route_advice(root, paths)
  closeout = sorted(checks | {"git diff --check", "./repo.sh agent_check"})
  return Report(
    paths=paths,
    skills=sorted(skills),
    notes=notes,
    closeout=closeout,
    stale=stale_doc_issues(root),
  )


def _render_list(title: str, values: list[str]) -> str:
  out = [title]
  if not values:
    out.append("  - none")
  else:
    out.extend(f"  - {v}" for v in values)
  return "\n".join(out)


def render_report(root: pathlib.Path, report: Report) -> str:
  parts = [
    "agent_check",
    f"root: {root}",
    "",
    _render_list("changed paths:", report.paths),
    "",
    _render_list("suggested skills:", report.skills),
    "",
    _render_list("routing notes:", report.notes),
    "",
    _render_list("suggested closeout checks:", report.closeout),
    "",
    _render_list("stale-doc issues:", report.stale),
  ]
  return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(prog="agent_check")
  parser.add_argument(
    "--stale-only",
    action="store_true",
    help="Print only stale-doc issues; exits non-zero if any are found.",
  )
  parser.add_argument(
    "--root",
    default=os.environ.get("REPO_ROOT") or os.getcwd(),
    help="Repository root (defaults to REPO_ROOT or cwd).",
  )
  args = parser.parse_args(argv)
  root = pathlib.Path(args.root).resolve()
  os.chdir(root)
  report = build_report(root)
  if args.stale_only:
    print(_render_list("stale-doc issues:", report.stale))
  else:
    print(render_report(root, report), end="")
  return 1 if report.stale else 0


if __name__ == "__main__":
  raise SystemExit(main())
