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
- ``ownership_issues(root, paths)`` — reports changed paths with zero or
  multiple primary owner Facets.
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
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from tools.facets import closeout_checks as facet_closeout_checks
from tools.facets import command_names as facet_command_names
from tools.facets import consideration_notes as facet_consideration_notes
from tools.facets import facet_consideration_conflicts
from tools.facets import facet_orphan_paths
from tools.facets import ownership_issues


SKILL_INDEX_REL = ".agents/skills/index.md"
SKILLS_DIR_REL = ".agents/skills"
AGENTS_REL = "AGENTS.md"
REPO_CONFIG_REL = ".agents/repo.json"
SCHEMA_DIR_REL = "schemas"


SCHEMA_FILES = (
  "repo.schema.json",
  "facet.schema.json",
  "idea.schema.json",
  "target.schema.json",
  "pyext.schema.json",
)


@dataclass
class Report:
  paths: list[str]
  skills: list[str]
  notes: list[str]
  closeout: list[str]
  ownership: list[str]
  stale: list[str]
  smoke: list[str]
  scorecard: list[dict[str, object]] | None = None

  @property
  def is_clean(self) -> bool:
    return not self.stale and not any(s.startswith("FAIL:") for s in self.smoke)


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


# ---- facet scorecard -------------------------------------------------------


def facet_budget_report(root: pathlib.Path) -> list[dict[str, object]]:
  """Parse all facet.json files and return sprawl scorecard.

  Returns list of dicts: {
    facet_name, commands_count, paths_count, check_count,
    stale_days, flags (list of: HIGH_COMMANDS, HIGH_PATHS, STALE, NO_OWNERSHIP)
  }
  """
  now = datetime.now(timezone.utc)
  facets_dir = root / ".agents/facet"
  scorecard: list[dict[str, object]] = []

  if not facets_dir.is_dir():
    return scorecard

  for facet_path in sorted(facets_dir.glob("*/facet.json")):
    facet_name = facet_path.parent.name
    try:
      facet_json = json.loads(facet_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
      continue

    commands = facet_json.get("commands", [])
    owns = facet_json.get("owns", [])
    checks = facet_json.get("checks", [])

    commands_count = len(commands) if isinstance(commands, list) else 0
    paths_count = len(owns) if isinstance(owns, list) else 0
    checks_count = len(checks) if isinstance(checks, list) else 0

    flags: list[str] = []

    # Check for sprawl: HIGH_COMMANDS (>5)
    if commands_count > 5:
      flags.append("HIGH_COMMANDS")

    # Check for sprawl: HIGH_PATHS (>8)
    if paths_count > 8:
      flags.append("HIGH_PATHS")

    # Check for stale: OWNERSHIP.md older than 90 days
    stale_days = None
    ownership_path = facet_path.parent / "OWNERSHIP.md"
    if ownership_path.exists():
      try:
        mtime = ownership_path.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        age = now - mtime_dt
        stale_days = age.days
        if stale_days > 90:
          flags.append("STALE")
      except OSError:
        pass
    else:
      if paths_count > 0:
        flags.append("NO_OWNERSHIP")

    scorecard.append(
      {
        "facet_name": facet_name,
        "commands_count": commands_count,
        "paths_count": paths_count,
        "checks_count": checks_count,
        "stale_days": stale_days,
        "flags": flags,
      }
    )

  return scorecard


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


def _facet_config(
    config: dict[str, object],
    facet: str,
) -> dict[str, object]:
  raw = config.get("facet_config", {})
  if not isinstance(raw, dict):
    raise ValueError(f"{REPO_CONFIG_REL}:facet_config must be object")
  value = raw.get(facet, {})
  if not isinstance(value, dict):
    raise ValueError(f"{REPO_CONFIG_REL}:facet_config.{facet} must be object")
  return value


def _str_list(raw: object, *, field: str) -> list[str]:
  if raw is None:
    return []
  if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
    raise ValueError(f"{REPO_CONFIG_REL}:{field} must be list[str]")
  return list(raw)


def _schema_str_list(raw: object, *, path: str, field: str) -> list[str]:
  if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw):
    raise ValueError(f"{path}:{field} must be non-empty string array")
  return list(raw)


def _schema_optional_str_list(raw: object, *, path: str, field: str) -> None:
  if raw is not None:
    _schema_str_list(raw, path=path, field=field)


def _schema_non_empty_str(raw: object, *, path: str, field: str) -> str:
  if not isinstance(raw, str) or not raw:
    raise ValueError(f"{path}:{field} must be non-empty string")
  return raw


def _schema_object(raw: object, *, path: str) -> dict[str, object]:
  if not isinstance(raw, dict):
    raise ValueError(f"{path} must be object")
  return raw


def _validate_repo_config_schema(root: pathlib.Path) -> list[str]:
  issues: list[str] = []
  rel = REPO_CONFIG_REL
  try:
    raw = _schema_object(json.loads((root / rel).read_text(encoding="utf-8")), path=rel)
    facet_config = raw.get("facet_config")
    if not isinstance(facet_config, dict):
      raise ValueError(f"{rel}:facet_config must be object")
    for name, config in facet_config.items():
      if not isinstance(name, str) or not name:
        raise ValueError(f"{rel}:facet_config keys must be non-empty strings")
      if not isinstance(config, dict):
        raise ValueError(f"{rel}:facet_config.{name} must be object")
  except (OSError, json.JSONDecodeError, ValueError) as exc:
    issues.append(f"schema validation failed: {exc}")
  return issues


def _validate_facet_schema(root: pathlib.Path) -> list[str]:
  issues: list[str] = []
  for path in sorted((root / ".agents/facet").glob("*/facet.json")):
    rel = path.relative_to(root).as_posix()
    try:
      raw = _schema_object(json.loads(path.read_text(encoding="utf-8")), path=rel)
      name = _schema_non_empty_str(raw.get("name"), path=rel, field="name")
      if name != path.parent.name and not (path.parent.name == "root" and name == "/"):
        raise ValueError(f"{rel}:name must match facet directory")
      _schema_non_empty_str(raw.get("description"), path=rel, field="description")
      _schema_str_list(raw.get("owns"), path=rel, field="owns")
      for field in ("commands", "checks", "docs", "consider"):
        value = raw.get(field, [])
        if not isinstance(value, list):
          raise ValueError(f"{rel}:{field} must be array")
      commands = raw.get("commands", [])
      if not isinstance(commands, list):
        raise ValueError(f"{rel}:commands must be array")
      for idx, command in enumerate(commands):
        if not isinstance(command, dict):
          raise ValueError(f"{rel}:commands[{idx}] must be object")
        _schema_non_empty_str(command.get("name"), path=rel, field=f"commands[{idx}].name")
        _schema_non_empty_str(command.get("purpose"), path=rel, field=f"commands[{idx}].purpose")
      checks = raw.get("checks", [])
      if not isinstance(checks, list):
        raise ValueError(f"{rel}:checks must be array")
      for idx, check in enumerate(checks):
        if not isinstance(check, dict):
          raise ValueError(f"{rel}:checks[{idx}] must be object")
        _schema_non_empty_str(check.get("name"), path=rel, field=f"checks[{idx}].name")
        _schema_non_empty_str(check.get("command"), path=rel, field=f"checks[{idx}].command")
      consider = raw.get("consider", [])
      if not isinstance(consider, list):
        raise ValueError(f"{rel}:consider must be array")
      for idx, consideration in enumerate(consider):
        if not isinstance(consideration, dict):
          raise ValueError(f"{rel}:consider[{idx}] must be object")
        _schema_str_list(consideration.get("paths"), path=rel, field=f"consider[{idx}].paths")
        _schema_optional_str_list(
          consideration.get("skills"), path=rel, field=f"consider[{idx}].skills"
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
      issues.append(f"schema validation failed: {exc}")
  return issues


def _validate_jsonl_schema(
    root: pathlib.Path,
    rel: str,
    required: tuple[str, ...],
) -> list[str]:
  issues: list[str] = []
  path = root / rel
  try:
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
      if not line.strip():
        continue
      row = _schema_object(json.loads(line), path=f"{rel}:{lineno}")
      for field in required:
        _schema_non_empty_str(row.get(field), path=f"{rel}:{lineno}", field=field)
  except (OSError, json.JSONDecodeError, ValueError) as exc:
    issues.append(f"schema validation failed: {exc}")
  return issues


def schema_issues(root: pathlib.Path) -> list[str]:
  issues: list[str] = []
  for name in SCHEMA_FILES:
    rel = f"{SCHEMA_DIR_REL}/{name}"
    path = root / rel
    try:
      schema = _schema_object(json.loads(path.read_text(encoding="utf-8")), path=rel)
      _schema_non_empty_str(schema.get("$schema"), path=rel, field="$schema")
      _schema_non_empty_str(schema.get("title"), path=rel, field="title")
      if schema.get("type") != "object":
        raise ValueError(f"{rel}:type must be object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
      issues.append(f"schema validation failed: {exc}")
  issues.extend(_validate_repo_config_schema(root))
  issues.extend(_validate_facet_schema(root))
  issues.extend(_validate_jsonl_schema(root, ".agents/targets/targets.jsonl", ("id", "title", "owner", "status")))
  issues.extend(_validate_jsonl_schema(root, ".agents/ideas/ideas.jsonl", ("id", "title", "owner", "state", "target")))
  return issues


def stale_skill_gates(root: pathlib.Path) -> list[str]:
  """Parse skill portfolio table and flag gates >180d old.

  Returns list of stale gate warnings: "STALE_SKILL_GATES: <skill> tier=<tier> age=<days>d last_reviewed=<date>"
  """
  from datetime import datetime, timezone, timedelta

  issues: list[str] = []
  index_path = root / SKILL_INDEX_REL
  if not index_path.exists():
    return issues

  text = _read(index_path)
  in_portfolio_table = False
  today = datetime.now(timezone.utc).date()
  max_age_days = 180

  for line in text.splitlines():
    # Detect skill portfolio section
    if "Skill Portfolio" in line:
      in_portfolio_table = True
      continue

    if in_portfolio_table:
      # Stop at next section (starts with ##)
      if line.startswith("##"):
        break

      # Skip non-table rows
      if not line.startswith("|"):
        continue

      # Parse table row
      cells = [c.strip() for c in line.strip("|").split("|")]
      if len(cells) < 4:
        continue

      # Skip header rows (if it starts with "Skill")
      if "Skill" in cells[0]:
        continue

      skill_cell = cells[0]
      tier_cell = cells[1]
      date_cell = cells[2]
      status_cell = cells[3] if len(cells) > 3 else ""

      # Extract skill name from backticks
      skill_match = re.search(r"`([a-z][a-z0-9_-]*)`", skill_cell)
      if not skill_match:
        continue
      skill_name = skill_match.group(1)

      # Extract date from cell (YYYY-MM-DD format)
      date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_cell)
      if not date_match:
        continue

      try:
        gate_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
        days_old = (today - gate_date).days
        if days_old > max_age_days:
          issues.append(
            f"STALE_SKILL_GATES: {skill_name} tier={tier_cell} age={days_old}d last_reviewed={date_match.group(1)}"
          )
      except ValueError:
        continue

  return issues


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
    if "_" in name:
      issues.append(
        f"skill folder name uses '_': {rel_skill} — skill names must use '-' "
        f"(template naming carve-out, see docs/adr/0004_skill_names_hyphens.md)"
      )
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

  configured_commands = facet_command_names(root)
  for command in configured_commands:
    tool = root / "tools" / command
    if not tool.is_file():
      issues.append(
        f".agents/facet/*/facet.json lists command `{command}` but tools/{command} not found"
      )
      continue
    if f"`{command}`" not in agents:
      issues.append(f"tool missing from AGENTS.md §8: tools/{command}")

  section_8 = _section(agents, r"## 8\.")
  for tn in sorted(set(re.findall(r"`([a-z][a-z0-9_-]*)`", section_8))):
    if tn not in configured_commands:
      issues.append(
        f"AGENTS.md §8 lists command `{tn}` but .agents/facet/*/facet.json does not"
      )

  root_config = _facet_config(config, "root")
  descriptor_globs = _str_list(
    root_config.get("subsystem_descriptor_globs"),
    field="facet_config.root.subsystem_descriptor_globs",
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


def _markdown_link_targets(text: str) -> list[str]:
  targets: list[str] = []
  for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
    target = match.group(1).strip()
    if (
        not target
        or target.startswith("#")
        or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)
    ):
      continue
    targets.append(target)
  return targets


def doc_coverage_issues(root: pathlib.Path) -> list[str]:
  issues: list[str] = []
  for path in sorted([root / "README.md", *list((root / "docs").rglob("*.md"))]):
    if not path.is_file():
      continue
    text = _read(path)
    base = path.parent
    rel = path.relative_to(root).as_posix()
    for target in _markdown_link_targets(text):
      target_path, _, _anchor = target.partition("#")
      if not target_path:
        continue
      if not (base / target_path).resolve().is_file():
        issues.append(f"markdown link missing in {rel}: {target}")

  for facet_path in sorted((root / ".agents/facet").glob("*/facet.json")):
    try:
      raw = json.loads(facet_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
      continue
    commands = raw.get("commands", [])
    if not isinstance(commands, list):
      continue
    for command in commands:
      if not isinstance(command, dict):
        continue
      name = command.get("name")
      if not isinstance(name, str):
        continue
      adr = command.get("adr")
      no_adr = command.get("no_adr")
      if isinstance(adr, str) and adr:
        if not (root / adr).is_file():
          issues.append(f"command `{name}` ADR missing: {adr}")
        continue
      if isinstance(no_adr, str) and no_adr:
        continue
      issues.append(f"command `{name}` missing adr or no_adr in {facet_path.relative_to(root)}")
  return issues


# ---- zig toolchain smoke ---------------------------------------------------


ZIG_SMOKE_C_SRC = "int main(void){return 0;}\n"
ZIG_SMOKE_CXX_SRC = "int main(){return 0;}\n"


def zig_smoke_target() -> str:
  arch = os.environ.get("REPO_ARCH") or platform.machine()
  match arch:
    case "amd64":
      arch = "x86_64"
    case "arm64":
      arch = "aarch64"
  return f"{arch}-linux-musl"


def zig_smoke(zig: str | None = None) -> tuple[bool, list[str]]:
  """Compile + run a trivial C and C++ program with the pinned Zig toolchain.

  Returns ``(passed, messages)``. ``passed`` is ``False`` only when zig is
  available *and* either compile/run step fails. If zig is not on ``PATH``
  the smoke is skipped and ``passed`` is ``True`` with a single warning
  message — fresh checkouts that have not run ``./repo.sh`` yet must not
  fail this check.

  Tests both ``zig cc`` (C, libc/musl) and ``zig c++`` (C++, libc++/musl)
  end-to-end against ADR-0013's pinned target ABI.
  """
  zig = zig or shutil.which("zig")
  if not zig:
    return True, ["zig_smoke: SKIP (zig not on PATH; run ./repo.sh first)"]

  messages: list[str] = []
  ok = True
  target = zig_smoke_target()
  with tempfile.TemporaryDirectory(prefix="zig_smoke_") as td:
    work = pathlib.Path(td)
    cases = [
      ("c", "cc", ZIG_SMOKE_C_SRC, "zig_smoke_c"),
      ("c++", "c++", ZIG_SMOKE_CXX_SRC, "zig_smoke_cxx"),
    ]
    for lang, driver, src, name in cases:
      src_path = work / f"{name}.{ 'cpp' if lang == 'c++' else 'c'}"
      bin_path = work / name
      src_path.write_text(src, encoding="utf-8")
      compile_proc = subprocess.run(
        [zig, driver, "-target", target,
         str(src_path), "-o", str(bin_path)],
        check=False, capture_output=True, text=True,
      )
      if compile_proc.returncode != 0:
        ok = False
        messages.append(
          f"zig_smoke: {lang} compile failed (rc={compile_proc.returncode}): "
          f"{compile_proc.stderr.strip().splitlines()[-1] if compile_proc.stderr else ''}"
        )
        continue
      run_proc = subprocess.run(
        [str(bin_path)], check=False, capture_output=True, text=True,
      )
      if run_proc.returncode != 0:
        ok = False
        messages.append(
          f"zig_smoke: {lang} run failed (rc={run_proc.returncode})"
        )
        continue
      messages.append(f"zig_smoke: {lang} OK ({target})")
  return ok, messages


# ---- pyext smoke -----------------------------------------------------------


def pyext_smoke_issues(root: pathlib.Path) -> list[str]:
  fixture = root / "tests/fixtures/pyext_smoke/mod.py"
  builder = root / "tools/pyext-build"
  if not fixture.is_file() or not builder.is_file():
    return []

  env = os.environ.copy()
  env.setdefault("REPO_ROOT", str(root))
  proc = subprocess.run(
    [str(builder), str(fixture)],
    cwd=root,
    check=False,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
  )
  if proc.returncode == 77:
    msg = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "unknown skip"
    return [f"SKIP: pyext smoke skipped: {msg}"]
  if proc.returncode != 0:
    msg = proc.stderr.strip() or proc.stdout.strip()
    return [f"FAIL: pyext smoke build failed: {msg}"]

  so_path = pathlib.Path(proc.stdout.strip().splitlines()[-1])
  if not so_path.is_file():
    return [f"FAIL: pyext smoke output missing: {so_path}"]

  import_proc = subprocess.run(
    [
      "python3",
      "-c",
      (
        "import importlib.util, pathlib; "
        "p = pathlib.Path(__import__('sys').argv[1]); "
        "spec = importlib.util.spec_from_file_location('mod', p); "
        "m = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(m); "
        "assert m.add(2, 3) == 5"
      ),
      str(so_path),
    ],
    cwd=root,
    check=False,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )
  if import_proc.returncode != 0:
    msg = import_proc.stderr.strip() or import_proc.stdout.strip()
    return [f"FAIL: pyext smoke import failed: {msg}"]

  readelf = shutil.which("readelf")
  if readelf:
    dyn = subprocess.run(
      [readelf, "-d", str(so_path)],
      cwd=root,
      check=False,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
    )
    if dyn.returncode != 0:
      msg = dyn.stderr.strip() or dyn.stdout.strip()
      return [f"FAIL: pyext smoke readelf failed: {msg}"]
    if "libc.so.6" in dyn.stdout:
      return [f"FAIL: pyext smoke found glibc dependency in {so_path}"]
  else:
    return ["SKIP: pyext smoke readelf check skipped: readelf not in PATH"]

  return [f"PASS: pyext smoke built and imported {so_path}"]


# ---- report assembly + CLI -------------------------------------------------


def build_report(root: pathlib.Path) -> Report:
  paths = changed_paths(root)
  skills, notes, checks = route_advice(root, paths)
  notes.extend(facet_consideration_notes(root, paths))
  closeout = sorted(
    checks
    | set(facet_closeout_checks(root, paths))
    | {"git diff --check", "./repo.sh agent_check"}
  )
  stale = stale_doc_issues(root)
  stale.extend(schema_issues(root))
  stale.extend(stale_skill_gates(root))
  stale.extend(facet_orphan_paths(root))
  stale.extend(facet_consideration_conflicts(root))
  smoke = pyext_smoke_issues(root)
  scorecard = facet_budget_report(root)
  return Report(
    paths=paths,
    skills=sorted(skills),
    notes=notes,
    closeout=closeout,
    ownership=ownership_issues(root, paths),
    stale=stale,
    smoke=smoke,
    scorecard=scorecard,
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
    _render_list("facet ownership issues:", report.ownership),
    "",
    _render_list("stale-doc issues:", report.stale),
    "",
    _render_list("smoke checks:", report.smoke),
  ]
  if report.scorecard:
    parts.extend(["", "facet scorecard:"])
    for entry in report.scorecard:
      flags_raw = entry.get("flags", [])
      flags = [flag for flag in flags_raw if isinstance(flag, str)] if isinstance(flags_raw, list) else []
      flags_str = ", ".join(flags)
      flags_display = f" [{flags_str}]" if flags_str else ""
      stale_display = f" stale={entry.get('stale_days')}d" if entry.get("stale_days") is not None else ""
      parts.append(
        f"  - {entry.get('facet_name')}: "
        f"commands={entry.get('commands_count')} "
        f"paths={entry.get('paths_count')} "
        f"checks={entry.get('checks_count')}{stale_display}{flags_display}"
      )
  return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(prog="agent_check")
  parser.add_argument(
    "--stale-only",
    action="store_true",
    help="Print only stale-doc issues; exits non-zero if any are found.",
  )
  parser.add_argument(
    "--zig-smoke",
    action="store_true",
    help=(
      "Run the C and C++ smoke tests against the pinned Zig toolchain "
      "(zig cc / zig c++ targeting x86_64-linux-musl). Skips cleanly with "
      "a warning if zig is not on PATH."
    ),
  )
  parser.add_argument(
    "--doc-cov",
    action="store_true",
    help="Check markdown links and command ADR coverage.",
  )
  parser.add_argument(
    "--root",
    default=os.environ.get("REPO_ROOT") or os.getcwd(),
    help="Repository root (defaults to REPO_ROOT or cwd).",
  )
  args = parser.parse_args(argv)
  root = pathlib.Path(args.root).resolve()
  os.chdir(root)
  if args.zig_smoke:
    ok, messages = zig_smoke()
    for m in messages:
      print(m)
    return 0 if ok else 1
  if args.doc_cov:
    issues = doc_coverage_issues(root)
    print(_render_list("doc coverage issues:", issues))
    return 1 if issues else 0
  if args.stale_only:
    stale = stale_doc_issues(root)
    stale.extend(schema_issues(root))
    stale.extend(stale_skill_gates(root))
    stale.extend(facet_orphan_paths(root))
    stale.extend(facet_consideration_conflicts(root))
    print(_render_list("stale-doc issues:", stale))
    return 1 if stale else 0
  else:
    report = build_report(root)
    print(render_report(root, report), end="")
  return 0 if report.is_clean else 1


if __name__ == "__main__":
  raise SystemExit(main())
