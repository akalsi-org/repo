"""Facet metadata loader and query helpers.

Facets are repo-level capability manifests under `.agents/facet/<name>/`.
Core tools consume these declarations so repo truth can move out of
hard-coded command lists without introducing executable plugins.
"""
from __future__ import annotations

import fnmatch
import json
import pathlib
from dataclasses import dataclass


FACETS_DIR_REL = ".agents/facet"


@dataclass(frozen=True)
class Consideration:
  paths: tuple[str, ...]
  reason: str
  skills: tuple[str, ...]


@dataclass(frozen=True)
class Command:
  name: str
  purpose: str


@dataclass(frozen=True)
class Check:
  name: str
  command: str
  closeout: bool


@dataclass(frozen=True)
class DocProjection:
  surface: str
  projection: str


@dataclass(frozen=True)
class Facet:
  name: str
  key: str
  description: str
  path: pathlib.Path
  owns: tuple[str, ...]
  consider: tuple[Consideration, ...]
  commands: tuple[Command, ...]
  checks: tuple[Check, ...]
  docs: tuple[DocProjection, ...]


@dataclass(frozen=True)
class FacetBudget:
  name: str
  owns: int
  considerations: int
  commands: int
  checks: int
  closeout_checks: int
  docs: int


@dataclass(frozen=True)
class FacetSpendBudget:
  facet_key: str
  facet_name: str
  max_spend: float
  unit: str
  period: str


def _require_object(
    raw: object,
    *,
    source: pathlib.Path,
    field: str | None = None,
) -> dict[str, object]:
  label = str(source) if field is None else f"{source}:{field}"
  if not isinstance(raw, dict):
    raise ValueError(f"{label} must be object")
  return dict(raw)


def _ensure_allowed_keys(
    raw: dict[str, object],
    *,
    allowed: set[str],
    source: pathlib.Path,
    field: str | None = None,
) -> None:
  extra = sorted(set(raw) - allowed)
  if not extra:
    return
  label = str(source) if field is None else f"{source}:{field}"
  extras = ", ".join(extra)
  raise ValueError(f"{label} has unknown key(s): {extras}")


def _require_non_empty_str(
    raw: object,
    *,
    field: str,
    source: pathlib.Path,
) -> str:
  if not isinstance(raw, str) or not raw:
    raise ValueError(f"{source}:{field} must be a non-empty string")
  return raw


def _str_list(
    raw: object,
    *,
    field: str,
    source: pathlib.Path,
) -> tuple[str, ...]:
  if raw is None:
    return ()
  if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw):
    raise ValueError(f"{source}:{field} must be list[str]")
  return tuple(raw)


def _object_list(
    raw: object,
    *,
    field: str,
    source: pathlib.Path,
) -> tuple[dict[str, object], ...]:
  if raw is None:
    return ()
  if not isinstance(raw, list) or not all(isinstance(v, dict) for v in raw):
    raise ValueError(f"{source}:{field} must be list[object]")
  return tuple(_require_object(v, source=source, field=field) for v in raw)


def _load_considerations(
    raw: object,
    *,
    source: pathlib.Path,
) -> tuple[Consideration, ...]:
  considerations: list[Consideration] = []
  for entry in _object_list(raw, field="consider", source=source):
    _ensure_allowed_keys(
      entry,
      allowed={"paths", "reason", "skills"},
      source=source,
      field="consider",
    )
    considerations.append(
      Consideration(
        paths=_str_list(entry.get("paths"), field="consider.paths", source=source),
        reason=_require_non_empty_str(
          entry.get("reason"),
          field="consider.reason",
          source=source,
        ),
        skills=_str_list(
          entry.get("skills"),
          field="consider.skills",
          source=source,
        ),
      )
    )
  return tuple(considerations)


def _load_commands(
    raw: object,
    *,
    source: pathlib.Path,
) -> tuple[Command, ...]:
  commands: list[Command] = []
  for entry in _object_list(raw, field="commands", source=source):
    _ensure_allowed_keys(
      entry,
      allowed={"name", "purpose"},
      source=source,
      field="commands",
    )
    commands.append(
      Command(
        name=_require_non_empty_str(
          entry.get("name"),
          field="commands.name",
          source=source,
        ),
        purpose=_require_non_empty_str(
          entry.get("purpose"),
          field="commands.purpose",
          source=source,
        ),
      )
    )
  return tuple(commands)


def _load_checks(
    raw: object,
    *,
    source: pathlib.Path,
) -> tuple[Check, ...]:
  checks: list[Check] = []
  for entry in _object_list(raw, field="checks", source=source):
    _ensure_allowed_keys(
      entry,
      allowed={"name", "command", "closeout"},
      source=source,
      field="checks",
    )
    closeout = entry.get("closeout", False)
    if not isinstance(closeout, bool):
      raise ValueError(f"{source}:checks.closeout must be bool")
    checks.append(
      Check(
        name=_require_non_empty_str(
          entry.get("name"),
          field="checks.name",
          source=source,
        ),
        command=_require_non_empty_str(
          entry.get("command"),
          field="checks.command",
          source=source,
        ),
        closeout=closeout,
      )
    )
  return tuple(checks)


def _load_docs(
    raw: object,
    *,
    source: pathlib.Path,
) -> tuple[DocProjection, ...]:
  docs: list[DocProjection] = []
  for entry in _object_list(raw, field="docs", source=source):
    _ensure_allowed_keys(
      entry,
      allowed={"surface", "projection"},
      source=source,
      field="docs",
    )
    docs.append(
      DocProjection(
        surface=_require_non_empty_str(
          entry.get("surface"),
          field="docs.surface",
          source=source,
        ),
        projection=_require_non_empty_str(
          entry.get("projection"),
          field="docs.projection",
          source=source,
        ),
      )
    )
  return tuple(docs)


def _load_facet(manifest: pathlib.Path) -> Facet:
  raw = _require_object(
    json.loads(manifest.read_text(encoding="utf-8")),
    source=manifest,
  )
  _ensure_allowed_keys(
    raw,
    allowed={"name", "description", "owns", "consider", "commands", "checks", "docs"},
    source=manifest,
  )

  key = manifest.parent.name
  name = _require_non_empty_str(raw.get("name"), field="name", source=manifest)
  if key == "root":
    if name != "/":
      raise ValueError(f"{manifest}:name must be '/' for root facet")
  elif name != key:
    raise ValueError(f"{manifest}:name must match facet directory")

  return Facet(
    name=name,
    key=key,
    description=_require_non_empty_str(
      raw.get("description"),
      field="description",
      source=manifest,
    ),
    path=manifest,
    owns=_str_list(raw.get("owns"), field="owns", source=manifest),
    consider=_load_considerations(raw.get("consider"), source=manifest),
    commands=_load_commands(raw.get("commands"), source=manifest),
    checks=_load_checks(raw.get("checks"), source=manifest),
    docs=_load_docs(raw.get("docs"), source=manifest),
  )


def _validate_facet_dedup(facet: Facet) -> None:
  """Check that facet does not have overlapping owns and consider.paths."""
  owns_set = {pattern for pattern in facet.owns}
  for consideration in facet.consider:
    for consider_path in consideration.paths:
      if consider_path in owns_set:
        raise ValueError(
          f"{facet.path}:owns and consider have overlapping path `{consider_path}` "
          f"in facet `{facet.name}` — remove from one list"
        )


def load_facets(root: pathlib.Path) -> list[Facet]:
  facets_dir = root / FACETS_DIR_REL
  if not facets_dir.exists():
    return []

  facets = [_load_facet(manifest) for manifest in sorted(facets_dir.glob("*/facet.json"))]
  
  # Validate command uniqueness
  command_owner: dict[str, pathlib.Path] = {}
  for facet in facets:
    for command in facet.commands:
      previous = command_owner.get(command.name)
      if previous is not None:
        raise ValueError(
          f"{facet.path}:commands.name `{command.name}` already declared by {previous}"
        )
      command_owner[command.name] = facet.path
  
  return facets


def facet_orphan_paths(root: pathlib.Path) -> list[str]:
  """Check for paths owned by facets that don't match actual files or directories.
  
  Returns list of error messages describing orphan patterns.
  """
  facets = load_facets(root)
  errors: list[str] = []
  
  # Build set of all known files and directories
  all_paths: set[str] = set()
  for item in root.rglob("*"):
    if item.is_file() or item.is_dir():
      rel_path = item.relative_to(root).as_posix()
      all_paths.add(rel_path)
      # Add parent directories
      for parent in pathlib.Path(rel_path).parents:
        if str(parent) != ".":
          all_paths.add(str(parent))
  
  # Check each facet's owns patterns
  for facet in facets:
    orphan_owns: list[str] = []
    for owns_pattern in facet.owns:
      # Check if this pattern matches any actual paths
      matched = any(
        glob_match(path, owns_pattern) for path in all_paths
      )
      # Skip patterns with ** or wildcards - they're too generic to validate
      if not matched and "**" not in owns_pattern and "*" not in owns_pattern:
        orphan_owns.append(owns_pattern)
    
    if orphan_owns:
      facet_name = facet.name or facet.key
      orphan_list = ", ".join(f"`{p}`" for p in orphan_owns)
      errors.append(
        f"facet `{facet_name}` owns {orphan_list} but these paths don't exist on disk"
      )
  
  return errors


def facet_consideration_conflicts(root: pathlib.Path) -> list[str]:
  """Check for paths in both 'owns' and 'consider' lists within a single facet.
  
  Returns list of error messages describing conflicts.
  """
  facets = load_facets(root)
  errors: list[str] = []
  
  for facet in facets:
    owns_set = set(facet.owns)
    for consideration in facet.consider:
      for consider_path in consideration.paths:
        if consider_path in owns_set:
          facet_name = facet.name or facet.key
          errors.append(
            f"facet `{facet_name}`: path `{consider_path}` in both owns and consider — "
            f"remove from one"
          )
  
  return errors


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


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
  return any(glob_match(path, pattern) for pattern in patterns)


def facet_keys(root: pathlib.Path) -> set[str]:
  return {facet.key for facet in load_facets(root)}


def owner_names(root: pathlib.Path, path: str) -> list[str]:
  names = [facet.name for facet in load_facets(root) if _matches_any(path, facet.owns)]
  return sorted(names)


def ownership_issues(root: pathlib.Path, paths: list[str]) -> list[str]:
  issues: list[str] = []
  for path in paths:
    owners = owner_names(root, path)
    if not owners:
      issues.append(
        f"facet ownership missing for changed path `{path}`: zero owner facets"
      )
    elif len(owners) > 1:
      owner_list = ", ".join(f"`{owner}`" for owner in owners)
      issues.append(
        f"facet ownership conflict for changed path `{path}`: "
        f"multiple owner facets ({owner_list})"
      )
  return issues


def command_names(root: pathlib.Path) -> list[str]:
  return sorted({command.name for facet in load_facets(root) for command in facet.commands})


def closeout_checks(root: pathlib.Path, paths: list[str]) -> list[str]:
  checks: set[str] = set()
  for facet in load_facets(root):
    if not any(_matches_any(path, facet.owns) for path in paths):
      continue
    for check in facet.checks:
      if check.closeout:
        checks.add(check.command)
  return sorted(checks)


def consideration_notes(root: pathlib.Path, paths: list[str]) -> list[str]:
  notes: list[str] = []
  for facet in load_facets(root):
    for entry in facet.consider:
      if not any(
          glob_match(path, pattern)
          for path in paths
          for pattern in entry.paths
      ):
        continue
      notes.append(f"consider `{facet.name}`: {entry.reason}")
  return sorted(set(notes))


def facet_budgets(root: pathlib.Path) -> list[FacetBudget]:
  budgets: list[FacetBudget] = []
  for facet in load_facets(root):
    budgets.append(
      FacetBudget(
        name=facet.name,
        owns=len(facet.owns),
        considerations=len(facet.consider),
        commands=len(facet.commands),
        checks=len(facet.checks),
        closeout_checks=sum(1 for check in facet.checks if check.closeout),
        docs=len(facet.docs),
      )
    )
  return budgets


def facet_spend_budgets(root: pathlib.Path) -> dict[str, FacetSpendBudget]:
  """Load Facet spend budgets from .agents/repo.json.
  
  Returns: dict[facet_key, FacetSpendBudget]
  Raises: ValueError if budget format is invalid
  """
  repo_json_path = root / ".agents/repo.json"
  if not repo_json_path.is_file():
    return {}
  
  repo_config = json.loads(repo_json_path.read_text(encoding="utf-8"))
  if not isinstance(repo_config, dict):
    return {}
  
  facet_budgets_raw = repo_config.get("facet_budgets")
  if facet_budgets_raw is None:
    return {}
  if not isinstance(facet_budgets_raw, dict):
    raise ValueError(".agents/repo.json:facet_budgets must be object")
  
  budgets: dict[str, FacetSpendBudget] = {}
  facets_by_key = {facet.key: facet for facet in load_facets(root)}
  
  for facet_key, budget_spec in facet_budgets_raw.items():
    if not isinstance(budget_spec, dict):
      raise ValueError(f".agents/repo.json:facet_budgets.{facet_key} must be object")
    
    # Parse max_spend like "5 days" or "10 hours"
    max_spend_str = budget_spec.get("max_spend")
    if not isinstance(max_spend_str, str) or not max_spend_str:
      raise ValueError(f".agents/repo.json:facet_budgets.{facet_key}.max_spend must be non-empty string")
    
    parts = max_spend_str.split()
    if len(parts) != 2:
      raise ValueError(
        f".agents/repo.json:facet_budgets.{facet_key}.max_spend format must be '<number> <unit>' (e.g., '5 days')"
      )
    
    try:
      max_spend = float(parts[0])
    except ValueError:
      raise ValueError(
        f".agents/repo.json:facet_budgets.{facet_key}.max_spend value must be numeric"
      )
    
    unit = parts[1].lower()  # "days", "hours"
    if unit not in ("days", "hours"):
      raise ValueError(
        f".agents/repo.json:facet_budgets.{facet_key}.max_spend unit must be 'days' or 'hours'"
      )
    
    period = budget_spec.get("period", "monthly")
    if not isinstance(period, str) or not period:
      raise ValueError(f".agents/repo.json:facet_budgets.{facet_key}.period must be non-empty string")
    
    facet = facets_by_key.get(facet_key)
    facet_name = facet.name if facet else facet_key
    
    budgets[facet_key] = FacetSpendBudget(
      facet_key=facet_key,
      facet_name=facet_name,
      max_spend=max_spend,
      unit=unit,
      period=period,
    )
  
  return budgets

