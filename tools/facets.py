"""Facet metadata loader.

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
class Facet:
  name: str
  key: str
  description: str
  path: pathlib.Path
  owns: tuple[str, ...]
  consider: tuple[dict[str, object], ...]
  commands: tuple[dict[str, str], ...]
  checks: tuple[dict[str, object], ...]
  docs: tuple[dict[str, str], ...]


def _str_list(raw: object, *, field: str, source: pathlib.Path) -> tuple[str, ...]:
  if raw is None:
    return ()
  if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
    raise ValueError(f"{source}:{field} must be list[str]")
  return tuple(raw)


def _dict_list(
    raw: object,
    *,
    field: str,
    source: pathlib.Path,
) -> tuple[dict[str, object], ...]:
  if raw is None:
    return ()
  if not isinstance(raw, list) or not all(isinstance(v, dict) for v in raw):
    raise ValueError(f"{source}:{field} must be list[object]")
  return tuple(dict(v) for v in raw)


def load_facets(root: pathlib.Path) -> list[Facet]:
  facets_dir = root / FACETS_DIR_REL
  if not facets_dir.exists():
    return []

  facets: list[Facet] = []
  for manifest in sorted(facets_dir.glob("*/facet.json")):
    key = manifest.parent.name
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
      raise ValueError(f"{manifest} must contain a JSON object")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
      raise ValueError(f"{manifest}:name must be a non-empty string")
    if key == "root":
      if name != "/":
        raise ValueError(f"{manifest}:name must be '/' for root facet")
    elif name != key:
      raise ValueError(f"{manifest}:name must match facet directory")

    description = raw.get("description")
    if not isinstance(description, str) or not description:
      raise ValueError(f"{manifest}:description must be a non-empty string")

    facets.append(
      Facet(
        name=name,
        key=key,
        description=description,
        path=manifest,
        owns=_str_list(raw.get("owns"), field="owns", source=manifest),
        consider=tuple(
          dict(v) for v in _dict_list(
            raw.get("consider"),
            field="consider",
            source=manifest,
          )
        ),
        commands=tuple(
          dict(v) for v in _dict_list(
            raw.get("commands"),
            field="commands",
            source=manifest,
          )
        ),
        checks=tuple(
          dict(v) for v in _dict_list(
            raw.get("checks"),
            field="checks",
            source=manifest,
          )
        ),
        docs=tuple(
          dict(v) for v in _dict_list(
            raw.get("docs"),
            field="docs",
            source=manifest,
          )
        ),
      )
    )
  return facets


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


def owner_names(root: pathlib.Path, path: str) -> list[str]:
  names: list[str] = []
  for facet in load_facets(root):
    if _matches_any(path, facet.owns):
      names.append(facet.name)
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
  names: set[str] = set()
  for facet in load_facets(root):
    for command in facet.commands:
      name = command.get("name")
      if isinstance(name, str) and name:
        names.add(name)
  return sorted(names)


def closeout_checks(root: pathlib.Path, paths: list[str]) -> list[str]:
  checks: set[str] = set()
  for facet in load_facets(root):
    if not any(_matches_any(path, facet.owns) for path in paths):
      continue
    for check in facet.checks:
      if check.get("closeout") is not True:
        continue
      command = check.get("command")
      if isinstance(command, str) and command:
        checks.add(command)
  return sorted(checks)


def consideration_notes(root: pathlib.Path, paths: list[str]) -> list[str]:
  notes: list[str] = []
  for facet in load_facets(root):
    for entry in facet.consider:
      raw_patterns = entry.get("paths", [])
      if not isinstance(raw_patterns, list) or not all(
          isinstance(v, str) for v in raw_patterns):
        raise ValueError(f"{facet.path}:consider.paths must be list[str]")
      if not any(
          glob_match(path, pattern)
          for path in paths
          for pattern in raw_patterns
      ):
        continue
      reason = entry.get("reason")
      if not isinstance(reason, str) or not reason:
        raise ValueError(f"{facet.path}:consider.reason must be non-empty string")
      notes.append(f"consider `{facet.name}`: {reason}")
  return sorted(set(notes))
