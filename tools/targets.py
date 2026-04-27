"""Target ledger loader and validators.

Canonical store: `.agents/targets/targets.jsonl`.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Iterator, Mapping

from tools.facets import facet_keys


TARGETS_REL = ".agents/targets/targets.jsonl"
TARGET_STATUSES = ("active", "archived")


@dataclass(frozen=True, slots=True)
class TargetRecord:
  id: str
  title: str
  owner: str
  status: str
  review_cadence: str | None = None
  check: str | None = None
  write_scope: tuple[str, ...] = ()
  parallel_mode: str | None = None
  blocker_target_id: str | None = None


class TargetLedger(Mapping[str, TargetRecord]):
  def __init__(self, ordered: tuple[TargetRecord, ...]) -> None:
    self.ordered = ordered
    self._by_id = {target.id: target for target in ordered}

  @classmethod
  def load(cls, root: pathlib.Path) -> "TargetLedger":
    path = root / TARGETS_REL
    if not path.is_file():
      raise ValueError(f"{TARGETS_REL} missing")
    owners = facet_keys(root)
    rows: list[TargetRecord] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
      if not line.strip():
        continue
      try:
        raw = json.loads(line)
      except json.JSONDecodeError as exc:
        raise ValueError(f"{TARGETS_REL}:{lineno}: invalid JSON: {exc.msg}") from exc
      if not isinstance(raw, dict):
        raise ValueError(f"{TARGETS_REL}:{lineno}: row must be object")
      target_id = raw.get("id")
      if not isinstance(target_id, str) or not target_id:
        raise ValueError(f"{TARGETS_REL}:{lineno}: id must be non-empty string")
      if target_id in seen:
        raise ValueError(f"{TARGETS_REL}:{lineno}: duplicate target id `{target_id}`")
      seen.add(target_id)
      title = raw.get("title")
      if not isinstance(title, str) or not title:
        raise ValueError(f"{TARGETS_REL}:{lineno}: title must be non-empty string")
      owner = raw.get("owner")
      if not isinstance(owner, str) or not owner:
        raise ValueError(f"{TARGETS_REL}:{lineno}: owner must be non-empty string")
      if owner not in owners:
        raise ValueError(f"{TARGETS_REL}:{lineno}: owner Facet `{owner}` missing")
      status = raw.get("status")
      if status not in TARGET_STATUSES:
        raise ValueError(
          f"{TARGETS_REL}:{lineno}: status must be one of {', '.join(TARGET_STATUSES)}"
        )
      review_cadence = raw.get("review_cadence")
      if review_cadence is not None and (
          not isinstance(review_cadence, str) or not review_cadence):
        raise ValueError(f"{TARGETS_REL}:{lineno}: review_cadence must be non-empty string")
      check = raw.get("check")
      if check is not None and (not isinstance(check, str) or not check):
        raise ValueError(f"{TARGETS_REL}:{lineno}: check must be non-empty string")
      write_scope_list = raw.get("write_scope")
      write_scope: tuple[str, ...] = ()
      if write_scope_list is not None:
        if not isinstance(write_scope_list, list):
          raise ValueError(f"{TARGETS_REL}:{lineno}: write_scope must be array of strings")
        for item in write_scope_list:
          if not isinstance(item, str) or not item:
            raise ValueError(f"{TARGETS_REL}:{lineno}: write_scope items must be non-empty strings")
        write_scope = tuple(write_scope_list)
      parallel_mode = raw.get("parallel_mode")
      if parallel_mode is not None and (not isinstance(parallel_mode, str) or parallel_mode not in ("safe", "serial", "blocked")):
        raise ValueError(f"{TARGETS_REL}:{lineno}: parallel_mode must be 'safe', 'serial', or 'blocked'")
      blocker_target_id = raw.get("blocker_target_id")
      if blocker_target_id is not None and (not isinstance(blocker_target_id, str) or not blocker_target_id):
        raise ValueError(f"{TARGETS_REL}:{lineno}: blocker_target_id must be non-empty string")
      rows.append(
        TargetRecord(
          id=target_id,
          title=title,
          owner=owner,
          status=status,
          review_cadence=review_cadence,
          check=check,
          write_scope=write_scope,
          parallel_mode=parallel_mode,
          blocker_target_id=blocker_target_id,
        )
      )
    return cls(tuple(rows))

  def __getitem__(self, key: str) -> TargetRecord:
    return self._by_id[key]

  def __iter__(self) -> Iterator[str]:
    return iter(self._by_id)

  def __len__(self) -> int:
    return len(self._by_id)

  def get(self, target_id: str) -> TargetRecord | None:
    return self._by_id.get(target_id)

  def require(
      self,
      target_id: object,
      /,
      *,
      field: str = "target",
      idea_id: str | None = None,
  ) -> TargetRecord:
    if not isinstance(target_id, str) or not target_id:
      raise ValueError(f"{field} must be non-empty string")
    target = self.get(target_id)
    if target is None:
      prefix = f"{idea_id}: " if idea_id else ""
      raise ValueError(f"{prefix}unknown {field} `{target_id}`")
    return target

  def active(self) -> tuple[TargetRecord, ...]:
    return tuple(target for target in self.ordered if target.status == "active")

  def validate_ref(
      self,
      value: object,
      *,
      field: str = "target",
      idea_id: str | None = None,
  ) -> list[str]:
    try:
      self.require(value, field=field, idea_id=idea_id)
    except ValueError as exc:
      return [str(exc)]
    return []

  def validate_idea_row(
      self,
      row: Mapping[str, object],
      /,
      *,
      field: str = "target",
  ) -> list[str]:
    idea_id = row.get("id")
    ident = idea_id if isinstance(idea_id, str) and idea_id else None
    return self.validate_ref(row.get(field), field=field, idea_id=ident)

  def validate_idea_rows(
      self,
      rows: list[Mapping[str, object]],
      /,
      *,
      field: str = "target",
  ) -> list[str]:
    issues: list[str] = []
    for row in rows:
      issues.extend(self.validate_idea_row(row, field=field))
    return issues


def load_target_ledger(root: pathlib.Path) -> TargetLedger:
  return TargetLedger.load(root)
