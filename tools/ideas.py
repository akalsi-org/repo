"""Idea inventory and backlog gate.

Canonical store: `.agents/ideas/ideas.jsonl`.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Mapping

ROOT = pathlib.Path(os.environ.get("REPO_ROOT") or pathlib.Path.cwd()).resolve()
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.facets import facet_budgets, facet_keys, facet_spend_budgets, glob_match
from tools.targets import TARGETS_REL, TargetLedger, TargetRecord, load_target_ledger


IDEAS_REL = ".agents/ideas/ideas.jsonl"
LEARNING_LEDGER_REL = ".agents/kb_src/tables/learning_ledger.jsonl"
LESSONS_REL = ".agents/ideas/lessons.jsonl"
STATES = ("seed", "shaped", "decided", "queued", "active", "done", "rejected", "parked")
SCORES = ("H", "M", "L")
VERDICTS = ("Do now", "Design first", "Watch", "Avoid")
QUEUE_READY_STATES = ("shaped", "decided", "queued")
COST_FIELDS = ("go_live_cost", "maintenance_overhead", "check_cost", "tool_sprawl")
PARALLEL_MODES = ("safe", "serial", "blocked")
WORKTREE_MODES = ("required", "recommended", "optional")
DACI_STR_FIELDS = ("driver", "approver")
DACI_LIST_FIELDS = ("contributors", "informed")
ACTIVE_STATES = {"seed", "shaped", "decided", "queued", "active"}
READY_STATE_PRIORITY = {"queued": 2, "decided": 1, "shaped": 0}
OUTCOME_REVIEW_FIELDS = ("expected", "actual", "follow_up", "reviewed_at")
LEARNING_LEDGER_SCHEMA_VERSION = "1.0"
LEARNING_LEDGER_REQUIRED_FIELDS = frozenset((
  "id",
  "lesson",
  "check",
  "facet",
  "reviewed_at",
  "source_idea",
  "target_id",
))
CADENCE_INTERVALS = {
  "daily": timedelta(days=1),
  "weekly": timedelta(days=7),
  "monthly": timedelta(days=30),
  "quarterly": timedelta(days=90),
  "yearly": timedelta(days=365),
}
NEXT_BET_ACTION_VERBS = (
  "add",
  "seed",
  "surface",
  "emit",
  "capture",
  "shape",
  "make",
  "use",
  "promote",
  "build",
  "derive",
  "synthesize",
)
NEXT_BET_DEFER_MARKERS = (
  "only if",
  "unless",
  "only after",
  "if ",
)
NEXT_BET_STOPWORDS = {
  "after",
  "around",
  "board",
  "cheap",
  "current",
  "decide",
  "delay",
  "fork",
  "from",
  "grow",
  "just",
  "keep",
  "make",
  "next",
  "only",
  "pass",
  "point",
  "real",
  "right",
  "seed",
  "shape",
  "should",
  "simple",
  "slice",
  "that",
  "then",
  "this",
  "unless",
  "until",
  "use",
  "visible",
  "when",
}


def utc_now() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ideas_path(root: pathlib.Path) -> pathlib.Path:
  return root / IDEAS_REL


def targets_path(root: pathlib.Path) -> pathlib.Path:
  return root / TARGETS_REL


def learning_ledger_path(root: pathlib.Path) -> pathlib.Path:
  return root / LEARNING_LEDGER_REL


def load_rows(root: pathlib.Path) -> list[dict[str, object]]:
  path = ideas_path(root)
  if not path.is_file():
    raise SystemExit(f"{IDEAS_REL} missing")
  rows: list[dict[str, object]] = []
  for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise SystemExit(f"{IDEAS_REL}:{lineno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(row, dict):
      raise SystemExit(f"{IDEAS_REL}:{lineno}: row must be object")
    rows.append(row)
  return rows


def write_rows(root: pathlib.Path, rows: list[dict[str, object]]) -> None:
  path = ideas_path(root)
  if not path.is_file():
    raise SystemExit(f"{IDEAS_REL} missing")
  text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
  path.write_text(text, encoding="utf-8")


def load_target_rows(root: pathlib.Path) -> list[dict[str, object]]:
  path = targets_path(root)
  if not path.is_file():
    raise SystemExit(f"{TARGETS_REL} missing")
  rows: list[dict[str, object]] = []
  for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise SystemExit(f"{TARGETS_REL}:{lineno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(row, dict):
      raise SystemExit(f"{TARGETS_REL}:{lineno}: row must be object")
    rows.append(row)
  return rows


def write_target_rows(root: pathlib.Path, rows: list[dict[str, object]]) -> None:
  path = targets_path(root)
  if not path.is_file():
    raise SystemExit(f"{TARGETS_REL} missing")
  path.write_text(
    "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
    encoding="utf-8",
  )


def load_learning_ledger_rows(root: pathlib.Path) -> list[dict[str, object]]:
  path = learning_ledger_path(root)
  if not path.is_file():
    return []
  rows: list[dict[str, object]] = []
  for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise SystemExit(f"{LEARNING_LEDGER_REL}:{lineno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(row, dict):
      raise SystemExit(f"{LEARNING_LEDGER_REL}:{lineno}: row must be object")
    # Validate required fields
    missing = LEARNING_LEDGER_REQUIRED_FIELDS - set(row.keys())
    if missing:
      raise SystemExit(f"{LEARNING_LEDGER_REL}:{lineno}: missing required fields: {sorted(missing)}")
    # Validate non-empty id and lesson
    if not row.get("id") or not isinstance(row["id"], str):
      raise SystemExit(f"{LEARNING_LEDGER_REL}:{lineno}: id must be non-empty string")
    if not row.get("lesson") or not isinstance(row["lesson"], str):
      raise SystemExit(f"{LEARNING_LEDGER_REL}:{lineno}: lesson must be non-empty string")
    rows.append(row)
  return rows


def write_learning_ledger_rows(root: pathlib.Path, rows: list[dict[str, object]]) -> None:
  path = learning_ledger_path(root)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _list_str(
    row: dict[str, object],
    field: str,
) -> list[str]:
  value = row.get(field)
  if not isinstance(value, list):
    return []
  return [item for item in value if isinstance(item, str)]


def _state_rank(row: dict[str, object]) -> int:
  state = row.get("state")
  if not isinstance(state, str):
    return -1
  return READY_STATE_PRIORITY.get(state, -1)


def _write_scope(row: dict[str, object]) -> list[str]:
  return _list_str(row, "write_scope")


def _scope_overlaps(left: str, right: str) -> bool:
  return glob_match(left, right) or glob_match(right, left)


def overlapping_scopes(
    left: dict[str, object],
    right: dict[str, object],
) -> list[str]:
  overlaps: list[str] = []
  for left_scope in _write_scope(left):
    for right_scope in _write_scope(right):
      if not _scope_overlaps(left_scope, right_scope):
        continue
      overlap = left_scope if left_scope == right_scope else f"{left_scope} <-> {right_scope}"
      if overlap not in overlaps:
        overlaps.append(overlap)
  return overlaps


def ready_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
  return [row for row in rows if is_queue_ready(row)]


def ready_conflicts(
    rows: list[dict[str, object]],
) -> list[tuple[dict[str, object], dict[str, object], list[str]]]:
  conflicts: list[tuple[dict[str, object], dict[str, object], list[str]]] = []
  for left, right in combinations(ready_rows(rows), 2):
    overlaps = overlapping_scopes(left, right)
    if overlaps:
      conflicts.append((left, right, overlaps))
  return conflicts


def _combo_batchable(combo: tuple[dict[str, object], ...]) -> bool:
  if len(combo) <= 1:
    return True
  for left, right in combinations(combo, 2):
    if left.get("parallel_mode") != "safe" or right.get("parallel_mode") != "safe":
      return False
    if overlapping_scopes(left, right):
      return False
  return True


def recommended_ready_batch(rows: list[dict[str, object]]) -> list[dict[str, object]]:
  ready = sorted(
    ready_rows(rows),
    key=lambda row: (-_state_rank(row), str(row.get("id"))),
  )
  best: tuple[dict[str, object], ...] = ()
  best_key = (-1, -1)
  for size in range(1, len(ready) + 1):
    for combo in combinations(ready, size):
      if not _combo_batchable(combo):
        continue
      key = (len(combo), sum(_state_rank(row) for row in combo))
      if key > best_key:
        best = combo
        best_key = key
  return list(best)


def _score_value(row: dict[str, object], field: str) -> str | None:
  score = row.get("score")
  if not isinstance(score, dict):
    return None
  value = score.get(field)
  if not isinstance(value, str):
    return None
  return value


def blocked_decision_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
  return [
    row for row in rows
    if row.get("decision_required") is True
    and row.get("state") in ACTIVE_STATES
  ]


def cost_risk_reasons(row: dict[str, object]) -> list[str]:
  reasons: list[str] = []
  maintenance = row.get("maintenance")
  if maintenance in {"M", "H"}:
    reasons.append(f"maintenance={maintenance}")
  for field in COST_FIELDS:
    value = row.get(field)
    if value in {"M", "H"}:
      reasons.append(f"{field}={value}")
  reversibility_score = _score_value(row, "reversibility")
  if reversibility_score in {"M", "L"}:
    reasons.append(f"reversibility_score={reversibility_score}")
  else:
    reversibility = row.get("reversibility")
    if isinstance(reversibility, str) and reversibility:
      lowered = reversibility.lower()
      if (
          "low" in lowered
          or "medium" in lowered
          or "irreversible" in lowered
      ):
        reasons.append(f"reversibility={reversibility}")
  return reasons


def cost_risk_rows(
    rows: list[dict[str, object]],
) -> list[tuple[dict[str, object], list[str]]]:
  risky: list[tuple[dict[str, object], list[str]]] = []
  for row in rows:
    if row.get("state") not in ACTIVE_STATES:
      continue
    reasons = cost_risk_reasons(row)
    if reasons:
      risky.append((row, reasons))
  return risky


def target_summary_rows(
    rows: list[dict[str, object]],
    ledger: TargetLedger,
    *,
    now: datetime,
) -> list[str]:
  lines: list[str] = []
  for target in ledger.ordered:
    assigned = [row for row in rows if row.get("target") == target.id]
    active = sum(1 for row in assigned if row.get("state") in ACTIVE_STATES)
    done = sum(1 for row in assigned if row.get("state") == "done")
    blocked = sum(1 for row in assigned if row.get("decision_required") is True)
    lifecycle = target_lifecycle(target, assigned)
    review_timing = target_review_timing(target, assigned, now=now)
    lines.append(
      f"{target.id} owner={target.owner} status={target.status} "
      f"active={active} done={done} blocked={blocked} "
      f"lifecycle={lifecycle['state']} "
      f"archive_candidate={lifecycle['archive_candidate']} "
      f"review={review_timing['state']} "
      f"last_reviewed={review_timing['last_reviewed']} "
      f"next_review_due={review_timing['next_review_due']}"
    )
  return lines


def _reviewed_at(row: dict[str, object]) -> datetime | None:
  outcome_review = row.get("outcome_review")
  if not isinstance(outcome_review, dict):
    return None
  reviewed_at = outcome_review.get("reviewed_at")
  if not isinstance(reviewed_at, str) or not reviewed_at:
    return None
  try:
    return datetime.fromisoformat(reviewed_at)
  except ValueError:
    return None


def _cadence_interval(cadence: str | None) -> timedelta | None:
  if cadence is None:
    return None
  return CADENCE_INTERVALS.get(cadence)


def target_review_timing(
    target: object,
    rows: list[dict[str, object]],
    *,
    now: datetime,
) -> dict[str, str]:
  cadence = getattr(target, "review_cadence", None)
  interval = _cadence_interval(cadence)
  reviewed = sorted(
    (seen for row in rows if (seen := _reviewed_at(row)) is not None),
  )
  last_reviewed = reviewed[-1] if reviewed else None
  if cadence is None:
    return {
      "state": "untracked",
      "last_reviewed": last_reviewed.isoformat() if last_reviewed else "never",
      "next_review_due": "n/a",
    }
  if interval is None:
    return {
      "state": "invalid_cadence",
      "last_reviewed": last_reviewed.isoformat() if last_reviewed else "never",
      "next_review_due": "unknown",
    }
  if last_reviewed is None:
    return {
      "state": "review_missing",
      "last_reviewed": "never",
      "next_review_due": "now",
    }
  next_due = last_reviewed + interval
  state = "overdue" if next_due <= now else "current"
  return {
    "state": state,
    "last_reviewed": last_reviewed.isoformat(),
    "next_review_due": next_due.isoformat(),
  }


def target_lifecycle(
    target: object,
    rows: list[dict[str, object]],
) -> dict[str, str]:
  has_active = any(row.get("state") in ACTIVE_STATES for row in rows)
  has_reviewed_done = any(
    row.get("state") == "done" and isinstance(row.get("outcome_review"), dict)
    for row in rows
  )
  if has_active:
    state = "active_work"
  elif has_reviewed_done:
    state = "proved_idle"
  else:
    state = "idle"
  archive_candidate = (
    "yes"
    if state == "proved_idle" and getattr(target, "status", None) == "active"
    else "no"
  )
  return {
    "state": state,
    "archive_candidate": archive_candidate,
  }


def derive_learning_ledger_rows(
    rows: list[dict[str, object]],
    ledger: TargetLedger,
) -> list[dict[str, object]]:
  archived_targets = {target.id for target in ledger.ordered if target.status == "archived"}
  derived: list[dict[str, object]] = []
  for row in rows:
    if row.get("state") != "done":
      continue
    target_id = row.get("target")
    if not isinstance(target_id, str) or target_id not in archived_targets:
      continue
    outcome_review = row.get("outcome_review")
    if not isinstance(outcome_review, dict):
      continue
    reviewed_at = outcome_review.get("reviewed_at")
    actual = outcome_review.get("actual")
    if not isinstance(reviewed_at, str) or not reviewed_at:
      continue
    if not isinstance(actual, str) or not actual:
      continue
    source_idea = row.get("id")
    if not isinstance(source_idea, str) or not source_idea:
      continue
    write_scope = row.get("write_scope")
    source_artifact = (
      write_scope[0]
      if isinstance(write_scope, list) and write_scope and isinstance(write_scope[0], str)
      else IDEAS_REL
    )
    checks = row.get("checks")
    check = (
      checks[0]
      if isinstance(checks, list) and checks and isinstance(checks[0], str)
      else ""
    )
    follow_up = outcome_review.get("follow_up")
    derived.append({
      "id": f"lesson_{source_idea}",
      "target_id": target_id,
      "facet": row.get("owner"),
      "source_idea": source_idea,
      "source_artifact": source_artifact,
      "check": check,
      "lesson": actual,
      "follow_up": follow_up if isinstance(follow_up, str) else "",
      "reviewed_at": reviewed_at,
    })
  return sorted(derived, key=lambda item: (str(item["reviewed_at"]), str(item["id"])))


def learning_ledger_freshness_issues(
    rows: list[dict[str, object]],
    ledger: TargetLedger,
    learning_rows: list[dict[str, object]],
) -> list[str]:
  expected = derive_learning_ledger_rows(rows, ledger)
  expected_ids = {
    str(row.get("id"))
    for row in expected
    if isinstance(row.get("id"), str) and row.get("id")
  }
  actual_ids = {
    str(row.get("id"))
    for row in learning_rows
    if isinstance(row.get("id"), str) and row.get("id")
  }
  missing = sorted(expected_ids - actual_ids)
  if not missing:
    return []
  parts: list[str] = ["learning_ledger stale:"]
  parts.append(f"missing={','.join(missing)}")
  parts.append("run_now=./repo.sh ideas sync_learning_ledger")
  return [" ".join(parts)]


def unused_active_targets(
    rows: list[dict[str, object]],
    ledger: TargetLedger,
) -> list[str]:
  used = {
    str(row.get("target"))
    for row in rows
    if isinstance(row.get("target"), str)
  }
  return [target.id for target in ledger.active() if target.id not in used]


def unreviewed_done_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
  return [
    row for row in rows
    if row.get("state") == "done" and not isinstance(row.get("outcome_review"), dict)
  ]


def _follow_up_text(row: dict[str, object]) -> str | None:
  outcome_review = row.get("outcome_review")
  if not isinstance(outcome_review, dict):
    return None
  follow_up = outcome_review.get("follow_up")
  if not isinstance(follow_up, str) or not follow_up.strip():
    return None
  return follow_up.strip()


def _learning_follow_up_text(row: Mapping[str, object]) -> str | None:
  follow_up = row.get("follow_up")
  if not isinstance(follow_up, str) or not follow_up.strip():
    return None
  return follow_up.strip()


def _text_tokens(text: str) -> set[str]:
  return {
    token
    for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    if len(token) >= 4 and token not in NEXT_BET_STOPWORDS
  }


def _row_timestamp(row: dict[str, object]) -> datetime | None:
  reviewed_at = _reviewed_at(row)
  if reviewed_at is not None:
    return reviewed_at
  updated_at = row.get("updated_at") or row.get("created_at")
  if not isinstance(updated_at, str) or not updated_at:
    return None
  try:
    return datetime.fromisoformat(updated_at)
  except ValueError:
    return None


def next_bet_follow_up_score(row: dict[str, object]) -> int:
  follow_up = _follow_up_text(row)
  if follow_up is None:
    return -99
  return next_bet_follow_up_score_text(follow_up)


def next_bet_follow_up_score_text(follow_up: str | None) -> int:
  if follow_up is None:
    return -99
  lowered = follow_up.lower()
  score = 0
  if lowered.startswith("next "):
    score += 3
  if lowered.startswith("next real slice:"):
    score += 2
  for verb in NEXT_BET_ACTION_VERBS:
    if lowered.startswith(f"{verb} ") or f" {verb} " in lowered:
      score += 2
  if any(token in lowered for token in ("review", "learning", "cadence", "signal", "fork", "ready bet")):
    score += 1
  if lowered.startswith("keep ") or lowered.startswith("delay ") or lowered.startswith("watch "):
    score -= 4
  for marker in NEXT_BET_DEFER_MARKERS:
    if marker in lowered:
      score -= 2
  return score


def _follow_up_already_addressed_text(
    follow_up: str | None,
    *,
    reviewed_at: datetime | None,
    source_id: object,
    rows: list[dict[str, object]],
) -> bool:
  if follow_up is None or reviewed_at is None:
    return False
  tokens = _text_tokens(follow_up)
  if len(tokens) < 2:
    return False
  for other in rows:
    if other.get("id") == source_id:
      continue
    other_time = _row_timestamp(other)
    if other_time is None or other_time < reviewed_at:
      continue
    if other.get("state") not in ACTIVE_STATES | {"done"}:
      continue
    haystack = " ".join(
      str(other.get(field, ""))
      for field in ("id", "title", "effect", "notes")
    )
    if len(tokens & _text_tokens(haystack)) >= 2:
      return True
  return False


def learning_next_bet_candidate(
    rows: list[dict[str, object]],
    learning_rows: list[dict[str, object]],
) -> dict[str, object] | None:
  candidates: list[tuple[int, str, dict[str, object]]] = []
  for row in learning_rows:
    follow_up = _learning_follow_up_text(row)
    reviewed_at = row.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at:
      continue
    score = next_bet_follow_up_score_text(follow_up)
    if score <= 1:
      continue
    try:
      reviewed_time = datetime.fromisoformat(reviewed_at)
    except ValueError:
      continue
    if _follow_up_already_addressed_text(
        follow_up,
        reviewed_at=reviewed_time,
        source_id=row.get("source_idea"),
        rows=rows,
    ):
      continue
    candidates.append((score, reviewed_at, row))
  if not candidates:
    return None
  score, reviewed_at, row = max(
    candidates,
    key=lambda item: (item[0], item[1], str(item[2].get("id"))),
  )
  return {
    "source_id": str(row.get("id")),
    "source_target": str(row.get("target_id")),
    "owner": str(row.get("facet")),
    "score": score,
    "reviewed_at": reviewed_at,
    "action": _learning_follow_up_text(row) or "",
    "check": str(row.get("check") or ""),
    "lesson": str(row.get("lesson") or ""),
    "source_artifact": str(row.get("source_artifact") or ""),
  }


def next_bet_candidate(
    rows: list[dict[str, object]],
    ledger: TargetLedger,
    learning_rows: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
  if learning_rows is not None:
    return learning_next_bet_candidate(rows, learning_rows)
  archived_targets = {target.id for target in ledger.ordered if target.status == "archived"}
  archived_reviewed: list[tuple[datetime, dict[str, object]]] = []
  candidates: list[tuple[int, datetime, dict[str, object]]] = []
  for row in rows:
    if row.get("state") != "done":
      continue
    target = row.get("target")
    if target not in archived_targets:
      continue
    follow_up = _follow_up_text(row)
    reviewed_at = _reviewed_at(row)
    if follow_up is None or reviewed_at is None:
      continue
    archived_reviewed.append((reviewed_at, row))
    score = next_bet_follow_up_score(row)
    if score <= 1:
      continue
    if follow_up_already_addressed(row, rows):
      continue
    candidates.append((score, reviewed_at, row))
  if not candidates:
    if len(archived_reviewed) < 3:
      return None
    reviewed_at, _ = max(archived_reviewed, key=lambda item: item[0])
    return {
      "source_id": "archived-outcomes",
      "source_target": "learning-ledger",
      "owner": "ideas",
      "score": 1,
      "reviewed_at": reviewed_at.isoformat(),
      "action": "add learning ledger from archived outcomes and reviews",
    }
  score, reviewed_at, row = max(
    candidates,
    key=lambda item: (item[0], item[1], str(item[2].get("id"))),
  )
  return {
    "source_id": str(row.get("id")),
    "source_target": str(row.get("target")),
    "owner": str(row.get("owner")),
    "score": score,
    "reviewed_at": reviewed_at.isoformat(),
    "action": _follow_up_text(row) or "",
  }


def follow_up_already_addressed(
    row: dict[str, object],
    rows: list[dict[str, object]],
) -> bool:
  return _follow_up_already_addressed_text(
    _follow_up_text(row),
    reviewed_at=_reviewed_at(row),
    source_id=row.get("id"),
    rows=rows,
  )


def validate_row(
    root: pathlib.Path,
    row: dict[str, object],
    *,
    ledger: TargetLedger,
) -> list[str]:
  issues: list[str] = []
  ident = row.get("id")
  if not isinstance(ident, str) or not ident:
    issues.append("id missing")
  state = row.get("state")
  if state not in STATES:
    issues.append(f"{ident or '<unknown>'}: invalid state {state!r}")
  owner = row.get("owner")
  if not isinstance(owner, str) or not owner:
    issues.append(f"{ident or '<unknown>'}: owner missing")
  elif owner not in facet_keys(root):
    issues.append(f"{ident or '<unknown>'}: owner Facet `{owner}` missing")
  issues.extend(ledger.validate_idea_row(row))
  checks = row.get("checks", [])
  if not isinstance(checks, list) or not all(isinstance(v, str) for v in checks):
    issues.append(f"{ident or '<unknown>'}: checks must be list[str]")
  decision_required = row.get("decision_required", False)
  if not isinstance(decision_required, bool):
    issues.append(f"{ident or '<unknown>'}: decision_required must be bool")
  score = row.get("score", {})
  if score is not None and not isinstance(score, dict):
    issues.append(f"{ident or '<unknown>'}: score must be object")
  for field in COST_FIELDS:
    value = row.get(field)
    if value is not None and value not in SCORES:
      issues.append(f"{ident or '<unknown>'}: {field} must be H, M, or L")
  parallel_mode = row.get("parallel_mode")
  if parallel_mode is not None and parallel_mode not in PARALLEL_MODES:
    issues.append(
      f"{ident or '<unknown>'}: parallel_mode must be safe, serial, or blocked")
  worktree = row.get("worktree")
  if worktree is not None and worktree not in WORKTREE_MODES:
    issues.append(
      f"{ident or '<unknown>'}: worktree must be required, recommended, or optional")
  write_scope = row.get("write_scope")
  if write_scope is not None and (
      not isinstance(write_scope, list)
      or not write_scope
      or not all(isinstance(v, str) and v for v in write_scope)
  ):
    issues.append(f"{ident or '<unknown>'}: write_scope must be non-empty list[str]")
  for field in DACI_STR_FIELDS:
    value = row.get(field)
    if value is not None and (not isinstance(value, str) or not value):
      issues.append(f"{ident or '<unknown>'}: {field} must be non-empty string")
  for field in DACI_LIST_FIELDS:
    value = row.get(field)
    if value is not None and (
        not isinstance(value, list)
        or not value
        or not all(isinstance(v, str) and v for v in value)
    ):
      issues.append(f"{ident or '<unknown>'}: {field} must be non-empty list[str]")
  outcome_review = row.get("outcome_review")
  if outcome_review is not None:
    if not isinstance(outcome_review, dict):
      issues.append(f"{ident or '<unknown>'}: outcome_review must be object")
    else:
      expected = outcome_review.get("expected")
      actual = outcome_review.get("actual")
      follow_up = outcome_review.get("follow_up")
      reviewed_at = outcome_review.get("reviewed_at")
      if not isinstance(expected, str) or not expected:
        issues.append(f"{ident or '<unknown>'}: outcome_review.expected must be non-empty string")
      if not isinstance(actual, str) or not actual:
        issues.append(f"{ident or '<unknown>'}: outcome_review.actual must be non-empty string")
      if follow_up is not None and (not isinstance(follow_up, str) or not follow_up):
        issues.append(f"{ident or '<unknown>'}: outcome_review.follow_up must be non-empty string")
      if not isinstance(reviewed_at, str) or not reviewed_at:
        issues.append(f"{ident or '<unknown>'}: outcome_review.reviewed_at must be non-empty string")
  return issues


def validate_rows(
    root: pathlib.Path,
    rows: list[dict[str, object]],
    *,
    ledger: TargetLedger,
) -> list[str]:
  issues: list[str] = []
  seen: set[str] = set()
  for row in rows:
    ident = row.get("id")
    if isinstance(ident, str) and ident:
      if ident in seen:
        issues.append(f"duplicate idea id `{ident}`")
      seen.add(ident)
    issues.extend(validate_row(root, row, ledger=ledger))
  return issues


def parse_cost_estimate(value: object) -> float | None:
  """Parse cost_estimate field (numeric value in days or hours)."""
  if value is None:
    return None
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value)
    except ValueError:
      return None
  return None


def facet_active_spend(rows: list[dict[str, object]], facet_key: str) -> float:
  """Calculate total LOE (in days) for active ideas in a Facet."""
  total = 0.0
  for row in rows:
    owner = row.get("owner")
    state = row.get("state")
    if owner != facet_key or state != "active":
      continue
    cost_estimate = parse_cost_estimate(row.get("cost_estimate"))
    if cost_estimate is not None:
      total += cost_estimate
  return total


def check_facet_budget(
    root: pathlib.Path,
    rows: list[dict[str, object]],
    facet_key: str,
    new_idea_cost: float | None = None,
) -> tuple[bool, str]:
  """Check if a Facet can accommodate new spend.
  
  Returns: (can_activate, message)
  - can_activate=True if within budget
  - message describes budget status
  """
  try:
    budgets = facet_spend_budgets(root)
  except ValueError as e:
    return True, f"budget_parse_error: {e}"
  
  if facet_key not in budgets:
    return True, "no_budget_configured"
  
  budget = budgets[facet_key]
  active_spend = facet_active_spend(rows, facet_key)
  total_spend = active_spend + (new_idea_cost or 0.0)
  
  if total_spend > budget.max_spend:
    return False, (
      f"BUDGET_EXCEEDED: Facet {budget.facet_name} would be at {100.0 * total_spend / budget.max_spend:.0f}% capacity "
      f"(active: {active_spend:.1f}{budget.unit}, new: {new_idea_cost or 0:.1f}{budget.unit}, "
      f"max: {budget.max_spend}{budget.unit})"
    )
  
  return True, (
    f"budget_ok: Facet {budget.facet_name} at {100.0 * total_spend / budget.max_spend:.0f}% capacity "
    f"({total_spend:.1f}/{budget.max_spend}{budget.unit})"
  )


def find_row(rows: list[dict[str, object]], ident: str) -> dict[str, object]:
  for row in rows:
    if row.get("id") == ident:
      return row
  raise SystemExit(f"unknown idea `{ident}`")


def find_learning_row(rows: list[dict[str, object]], ident: str) -> dict[str, object]:
  for row in rows:
    if row.get("id") == ident:
      return row
  raise SystemExit(f"unknown learning lesson `{ident}`")


def parse_check(values: list[str]) -> list[str]:
  return list(dict.fromkeys(values))


def evidence_note(lesson: Mapping[str, object]) -> str:
  fields = (
    ("lesson", lesson.get("id")),
    ("source_idea", lesson.get("source_idea")),
    ("artifact", lesson.get("source_artifact")),
    ("check", lesson.get("check")),
    ("reviewed_at", lesson.get("reviewed_at")),
    ("follow_up", lesson.get("follow_up")),
  )
  return "evidence: " + " ".join(
    f"{name}={value}"
    for name, value in fields
    if isinstance(value, str) and value
  )


def _slugify(text: str) -> str:
  slug = "-".join(
    part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    if part
  )
  return slug or "lesson"


def _humanize_slug(text: str) -> str:
  return " ".join(part.capitalize() for part in text.replace("-", " ").split()) or "Lesson"


def derive_activation_defaults(lesson: Mapping[str, object]) -> dict[str, str]:
  lesson_id = str(lesson.get("id") or "lesson")
  source_idea = str(lesson.get("source_idea") or lesson_id.removeprefix("lesson_"))
  source_target = str(lesson.get("target_id") or source_idea)
  target_id = _slugify(f"{source_target} follow up")
  idea_id = _slugify(f"{source_idea} follow up")
  target_title = _humanize_slug(target_id)
  follow_up = _learning_follow_up_text(lesson)
  if follow_up is not None:
    idea_title = follow_up[:1].upper() + follow_up[1:]
    effect = f"Follow up lesson {lesson_id}: {follow_up}"
  else:
    lesson_text = str(lesson.get("lesson") or lesson_id)
    idea_title = _humanize_slug(idea_id)
    effect = f"Follow up lesson {lesson_id}: {lesson_text}"
  return {
    "target_id": target_id,
    "target_title": target_title,
    "idea_id": idea_id,
    "idea_title": idea_title,
    "effect": effect,
  }


def _match_filter(value: object, expected: str | None, *, exact: bool) -> bool:
  if expected is None:
    return True
  if not isinstance(value, str):
    return False
  return value == expected if exact else expected in value


def filter_learning_rows(
    rows: list[dict[str, object]],
    *,
    facet: str | None = None,
    target: str | None = None,
    check: str | None = None,
    artifact: str | None = None,
) -> list[dict[str, object]]:
  filtered: list[dict[str, object]] = []
  for row in rows:
    if not _match_filter(row.get("facet"), facet, exact=True):
      continue
    if not _match_filter(row.get("target_id"), target, exact=True):
      continue
    if not _match_filter(row.get("check"), check, exact=False):
      continue
    if not _match_filter(row.get("source_artifact"), artifact, exact=False):
      continue
    filtered.append(row)
  return filtered


def pick_learning_row(
    rows: list[dict[str, object]],
    *,
    lesson_id: str | None,
    facet: str | None,
    target: str | None,
    check: str | None,
    artifact: str | None,
) -> dict[str, object]:
  if lesson_id is not None:
    return find_learning_row(rows, lesson_id)
  filtered = filter_learning_rows(
    rows,
    facet=facet,
    target=target,
    check=check,
    artifact=artifact,
  )
  if not filtered:
    raise SystemExit("activate_next_bet needs --lesson-id or filters matching one lesson")
  if len(filtered) > 1:
    matches = ",".join(str(row.get("id")) for row in filtered[:5])
    raise SystemExit(f"activate_next_bet matched multiple lessons: {matches}")
  return filtered[0]


def is_queue_ready(row: dict[str, object]) -> bool:
  return not readiness_blockers(row)


def queue_blockers(row: dict[str, object]) -> list[str]:
  blockers: list[str] = []
  if row.get("state") not in {"shaped", "decided", "queued"}:
    blockers.append(f"state {row.get('state')}")
  if row.get("decision_required") is True:
    blockers.append("decision required")
  required = ("target", "reversibility")
  for key in required:
    if not isinstance(row.get(key), str) or not row.get(key):
      blockers.append(f"missing {key}")
  checks = row.get("checks", [])
  if not isinstance(checks, list) or not checks:
    blockers.append("missing checks")
  return blockers


def readiness_blockers(row: dict[str, object]) -> list[str]:
  blockers = queue_blockers(row)
  if not row.get("parallel_mode"):
    blockers.append("missing parallel_mode")
  if not row.get("worktree"):
    blockers.append("missing worktree")
  if not row.get("write_scope"):
    blockers.append("missing write_scope")
  return blockers


def ready_suffix(row: dict[str, object]) -> str:
  parts: list[str] = []
  for field in ("parallel_mode", "worktree"):
    value = row.get(field)
    if isinstance(value, str) and value:
      name = "parallel" if field == "parallel_mode" else field
      parts.append(f"{name}={value}")
  write_scope = row.get("write_scope")
  if isinstance(write_scope, list) and write_scope:
    parts.append("scope=" + ",".join(str(v) for v in write_scope))
  driver = row.get("driver")
  approver = row.get("approver")
  if isinstance(driver, str) and driver:
    if isinstance(approver, str) and approver:
      parts.append(f"daci={driver}->{approver}")
    else:
      parts.append(f"driver={driver}")
  return f" [{' '.join(parts)}]" if parts else ""


def get_git_user() -> tuple[str, str]:
  """Get git user name and email."""
  try:
    name = subprocess.check_output(
      ["git", "config", "user.name"],
      stderr=subprocess.DEVNULL,
      text=True,
    ).strip()
    email = subprocess.check_output(
      ["git", "config", "user.email"],
      stderr=subprocess.DEVNULL,
      text=True,
    ).strip()
    return (name, email)
  except (subprocess.CalledProcessError, FileNotFoundError):
    raise SystemExit("git config user.name and user.email must be set")


def load_lessons_rows(root: pathlib.Path) -> list[dict[str, object]]:
  """Load lessons from .agents/ideas/lessons.jsonl."""
  path = root / LESSONS_REL
  if not path.is_file():
    return []
  rows: list[dict[str, object]] = []
  for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise SystemExit(f"{LESSONS_REL}:{lineno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(row, dict):
      raise SystemExit(f"{LESSONS_REL}:{lineno}: row must be object")
    rows.append(row)
  return rows


def write_lessons_rows(root: pathlib.Path, rows: list[dict[str, object]]) -> None:
  """Write lessons to .agents/ideas/lessons.jsonl."""
  path = root / LESSONS_REL
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def cmd_activate_dry_run(root: pathlib.Path, args: argparse.Namespace) -> int:
  """Output activation receipt for target without side effects."""
  target_rows = load_target_rows(root)
  target_id = args.target_id
  
  # Find target
  target_row = None
  for row in target_rows:
    if row.get("id") == target_id:
      target_row = row
      break
  
  if not target_row:
    raise SystemExit(f"target `{target_id}` not found")
  
  # Validate required fields
  check = target_row.get("check")
  if not check:
    raise SystemExit(f"target `{target_id}` has no check")
  
  owner = target_row.get("owner")
  if not owner:
    raise SystemExit(f"target `{target_id}` has no owner")
  
  write_scope = target_row.get("write_scope")
  if not write_scope:
    raise SystemExit(f"target `{target_id}` has no write_scope")
  
  estimated_loe = target_row.get("estimated_loe", "1w")
  
  # Build receipt
  receipt = {
    "target_id": target_id,
    "check": check,
    "write_scope": write_scope,
    "owner_facet": owner,
    "estimated_loe": estimated_loe,
    "ready_timestamp": datetime.now(timezone.utc).isoformat(),
    "activation_command": f"ideas activate --target {target_id}",
  }
  
  print(json.dumps(receipt, sort_keys=True))
  return 0


def cmd_activate(root: pathlib.Path, args: argparse.Namespace) -> int:
  """Activate a target by setting activated_at and activated_by."""
  target_rows = load_target_rows(root)
  target_id = args.target
  
  # Find target
  target_row = None
  target_idx = None
  for idx, row in enumerate(target_rows):
    if row.get("id") == target_id:
      target_row = row
      target_idx = idx
      break
  
  if not target_row:
    raise SystemExit(f"target `{target_id}` not found")
  
  if target_row.get("status") != "active":
    raise SystemExit(f"target `{target_id}` is not active (status={target_row.get('status')})")
  
  # Check if already activated
  if target_row.get("activated_at"):
    print(f"Target {target_id} already activated at {target_row.get('activated_at')}")
    return 0
  
  # Get git user
  user_name, user_email = get_git_user()
  
  # Update target
  now = datetime.now(timezone.utc).isoformat()
  target_row = dict(target_row)  # Make mutable copy
  target_row["activated_at"] = now
  target_row["activated_by"] = user_email
  target_rows[target_idx] = target_row
  
  write_target_rows(root, target_rows)
  
  # Calculate review date
  check = target_row.get("check", "")
  review_cadence = target_row.get("review_cadence", "weekly")
  interval = CADENCE_INTERVALS.get(review_cadence, timedelta(days=7))
  review_date = (datetime.now(timezone.utc) + interval).strftime("%Y-%m-%d")
  
  print(f"Target {target_id} activated.")
  print(f"Run check: {check}")
  print(f"Expected review date: {review_date}")
  return 0


def cmd_archive(root: pathlib.Path, args: argparse.Namespace) -> int:
  """Archive a target with outcome and optionally prompt for lesson."""
  target_rows = load_target_rows(root)
  target_id = args.target_id
  outcome = args.outcome
  
  if outcome not in ("pass", "fail"):
    raise SystemExit(f"outcome must be 'pass' or 'fail', got '{outcome}'")
  
  # Find target
  target_row = None
  target_idx = None
  for idx, row in enumerate(target_rows):
    if row.get("id") == target_id:
      target_row = row
      target_idx = idx
      break
  
  if not target_row:
    raise SystemExit(f"target `{target_id}` not found")
  
  if target_row.get("status") != "active":
    raise SystemExit(f"target `{target_id}` is not active (status={target_row.get('status')})")
  
  # Get git user
  user_name, user_email = get_git_user()
  
  # Update target
  now = datetime.now(timezone.utc).isoformat()
  target_row = dict(target_row)  # Make mutable copy
  target_row["archived_at"] = now
  target_row["outcome"] = outcome
  target_row["archived_by"] = user_email
  target_rows[target_idx] = target_row
  
  # If outcome is fail, mark for revisit
  if outcome == "fail":
    target_row["to_revisit"] = True
  
  write_target_rows(root, target_rows)
  
  # If outcome is pass, prompt for lesson
  if outcome == "pass":
    print(f"Target {target_id} achieved outcome: pass")
    print("Enter a 1-line lesson learned (or press Enter to skip):")
    try:
      lesson_text = input().strip()
    except (EOFError, KeyboardInterrupt):
      lesson_text = ""
    
    if lesson_text:
      # Create lesson entry
      lessons = load_lessons_rows(root)
      
      lesson_id = f"lesson-{target_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
      lesson_row = {
        "id": lesson_id,
        "lesson": lesson_text,
        "check": target_row.get("check", ""),
        "facet": target_row.get("owner", ""),
        "reviewed_at": now,
        "source_target_id": target_id,
        "reviewed_by": user_email,
        "outcome": "pass",
      }
      
      lessons.append(lesson_row)
      write_lessons_rows(root, lessons)
      print(f"Lesson recorded: {lesson_id}")
    else:
      print("No lesson recorded")
  else:
    # outcome == fail
    print(f"Target {target_id} achieved outcome: fail")
    print("Enter failure reason (or press Enter to skip):")
    try:
      failure_reason = input().strip()
    except (EOFError, KeyboardInterrupt):
      failure_reason = ""
    
    if failure_reason:
      target_rows[target_idx]["failure_reason"] = failure_reason
      write_target_rows(root, target_rows)
      print(f"Failure reason recorded: {failure_reason}")
    
    print("Target marked for revisit in next board cycle.")
  
  return 0


def cmd_list(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  if args.state:
    rows = [row for row in rows if row.get("state") == args.state]
  if args.owner:
    rows = [row for row in rows if row.get("owner") == args.owner]
  if args.json:
    print(json.dumps({"ideas": rows}, sort_keys=True))
    return 0

  if not rows:
    print("ideas: none")
    return 0
  for row in rows:
    ready = " ready" if is_queue_ready(row) else ""
    print(f"{row['id']}: {row.get('state')} owner={row.get('owner')}{ready}")
    print(f"  {row.get('title', '')}")
  return 0


def cmd_add(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  if any(row.get("id") == args.id for row in rows):
    raise SystemExit(f"idea `{args.id}` already exists")
  if args.owner not in facet_keys(root):
    raise SystemExit(f"owner Facet `{args.owner}` missing")
  now = utc_now()
  row: dict[str, object] = {
    "id": args.id,
    "title": args.title,
    "owner": args.owner,
    "state": args.state,
    "target": args.target,
    "effect": args.effect,
    "checks": parse_check(args.check),
    "reversibility": args.reversibility,
    "maintenance": args.maintenance,
    "decision_required": args.decision_required,
    "notes": args.notes or "",
    "created_at": now,
    "updated_at": now,
  }
  for field in COST_FIELDS:
    value = getattr(args, field)
    if value is not None:
      row[field] = value
  for field in DACI_STR_FIELDS:
    value = getattr(args, field)
    if value is not None:
      row[field] = value
  daci_list_args = {
    "contributors": args.contributor,
    "informed": args.informed,
  }
  for field, value in daci_list_args.items():
    if value is not None:
      row[field] = parse_check(value)
  if args.parallel_mode is not None:
    row["parallel_mode"] = args.parallel_mode
  if args.worktree is not None:
    row["worktree"] = args.worktree
  if args.write_scope is not None:
    row["write_scope"] = parse_check(args.write_scope)
  issues = validate_row(root, row, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  rows.append(row)
  write_rows(root, rows)
  print(f"added {args.id}")
  return 0


def cmd_score(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  row = find_row(rows, args.id)
  row["score"] = {
    "return": args.return_score,
    "time_sink": args.time_sink,
    "go_live": args.go_live,
    "maintenance": args.maintenance_score,
    "reversibility": args.reversibility_score,
    "fit": args.fit,
    "verdict": args.verdict,
  }
  if hasattr(args, 'cost_estimate') and args.cost_estimate is not None:
    row["cost_estimate"] = args.cost_estimate
  row["updated_at"] = utc_now()
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  write_rows(root, rows)
  output = f"scored {args.id}"
  if hasattr(args, 'cost_estimate') and args.cost_estimate is not None:
    can_activate, msg = check_facet_budget(root, rows, row.get("owner"), args.cost_estimate)
    if not can_activate:
      print(f"{output} with WARNING: {msg}")
    else:
      print(f"{output} ({msg})")
  else:
    print(output)
  return 0


def cmd_promote(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  row = find_row(rows, args.id)
  blockers = queue_blockers(row)
  if args.state == "queued" and blockers:
    raise SystemExit(
      "cannot queue: " + ", ".join(blockers)
  )
  row["state"] = args.state
  row["updated_at"] = utc_now()
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  write_rows(root, rows)
  print(f"{args.id} -> {args.state}")
  return 0


def cmd_shape_from_decision(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  if any(row.get("id") == args.id for row in rows):
    raise SystemExit(f"idea `{args.id}` already exists")
  owner = args.owner or "ideas"
  if owner not in facet_keys(root):
    raise SystemExit(f"owner Facet `{owner}` missing")
  now = utc_now()
  row: dict[str, object] = {
    "id": args.id,
    "title": args.title,
    "owner": owner,
    "state": "shaped",
    "target": args.target,
    "effect": args.recommendation,
    "checks": [],
    "reversibility": "high",
    "maintenance": "L",
    "decision_required": False,
    "notes": f"board decision: {args.recommendation}" + (
      f" (link: {args.link})" if args.link else ""
    ),
    "created_at": now,
    "updated_at": now,
  }
  issues = validate_row(root, row, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  rows.append(row)
  write_rows(root, rows)
  print(f"shaped {args.id} from board decision")
  return 0


def cmd_park(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  row = find_row(rows, args.id)
  row["state"] = "parked"
  row["park_reason"] = args.reason
  row["updated_at"] = utc_now()
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  write_rows(root, rows)
  print(f"parked {args.id}")
  return 0


def cmd_review(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  row = find_row(rows, args.id)
  if row.get("state") != "done":
    raise SystemExit("can review only done ideas")
  row["outcome_review"] = {
    "expected": args.expected,
    "actual": args.actual,
    "follow_up": args.follow_up or "",
    "reviewed_at": utc_now(),
  }
  issues = validate_row(root, row, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  row["updated_at"] = utc_now()
  write_rows(root, rows)
  print(f"reviewed {args.id}")
  return 0


def cmd_activate_next_bet(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  target_rows = load_target_rows(root)
  ledger = load_target_ledger(root)
  learning_rows = load_learning_ledger_rows(root)
  if not learning_rows:
    raise SystemExit(f"{LEARNING_LEDGER_REL} missing or empty")
  freshness_issues = learning_ledger_freshness_issues(rows, ledger, learning_rows)
  if freshness_issues:
    raise SystemExit("\n".join(freshness_issues))
  lesson = pick_learning_row(
    learning_rows,
    lesson_id=args.lesson_id,
    facet=args.facet,
    target=args.target,
    check=args.check_filter,
    artifact=args.artifact,
  )
  defaults = derive_activation_defaults(lesson)
  target_id = args.target_id or defaults["target_id"]
  target_title = args.target_title or defaults["target_title"]
  idea_id = args.idea_id or defaults["idea_id"]
  idea_title = args.idea_title or defaults["idea_title"]
  effect = args.effect or defaults["effect"]
  if any(row.get("id") == idea_id for row in rows):
    raise SystemExit(f"idea `{idea_id}` already exists")
  if ledger.get(target_id) is not None:
    raise SystemExit(f"target `{target_id}` already exists")
  owner = args.owner or lesson.get("facet")
  if not isinstance(owner, str) or not owner:
    raise SystemExit("owner missing from lesson and no --owner supplied")
  if owner not in facet_keys(root):
    raise SystemExit(f"owner Facet `{owner}` missing")
  checks = parse_check(args.check) if args.check else parse_check([
    str(lesson.get("check") or ""),
  ])
  checks = [check for check in checks if check]
  if not checks:
    raise SystemExit("activate_next_bet needs at least one check")
  if args.write_scope:
    write_scope = parse_check(args.write_scope)
  else:
    source_artifact = lesson.get("source_artifact")
    if not isinstance(source_artifact, str) or not source_artifact:
      raise SystemExit("activate_next_bet needs --write-scope when lesson has no source_artifact")
    write_scope = [source_artifact]
  
  # Check Facet budget hard gate
  cost_estimate = parse_cost_estimate(getattr(args, 'cost_estimate', None))
  can_activate, budget_msg = check_facet_budget(root, rows, owner, cost_estimate)
  if not can_activate:
    active_ideas = [
      f"{r.get('id')} ({r.get('cost_estimate', 'unknown')}d)"
      for r in rows if r.get("owner") == owner and r.get("state") == "active"
    ]
    raise SystemExit(
      f"Facet budget ceiling exceeded. {budget_msg}\n"
      f"Active targets: {', '.join(active_ideas) if active_ideas else 'none'}\n"
      f"Archive or finish one before activating."
    )
  
  new_target = TargetRecord(
    id=target_id,
    title=target_title,
    owner=owner,
    status="active",
    review_cadence=args.review_cadence,
    check=checks[0],
  )
  temp_ledger = TargetLedger((*ledger.ordered, new_target))
  now = utc_now()
  note_parts = [evidence_note(lesson)]
  if args.notes:
    note_parts.append(args.notes)
  row: dict[str, object] = {
    "id": idea_id,
    "title": idea_title,
    "owner": owner,
    "state": args.state,
    "target": target_id,
    "effect": effect,
    "checks": checks,
    "reversibility": args.reversibility,
    "maintenance": args.maintenance,
    "go_live_cost": args.go_live_cost,
    "maintenance_overhead": args.maintenance_overhead,
    "check_cost": args.check_cost,
    "tool_sprawl": args.tool_sprawl,
    "parallel_mode": args.parallel_mode,
    "worktree": args.worktree,
    "write_scope": write_scope,
    "decision_required": False,
    "notes": " ".join(part for part in note_parts if part),
    "created_at": now,
    "updated_at": now,
    "source_lesson": str(lesson.get("id") or ""),
    "source_target": str(lesson.get("target_id") or ""),
    "source_check": str(lesson.get("check") or ""),
    "source_artifact": str(lesson.get("source_artifact") or ""),
    "source_reviewed_at": str(lesson.get("reviewed_at") or ""),
  }
  if cost_estimate is not None:
    row["cost_estimate"] = cost_estimate
  for field in DACI_STR_FIELDS:
    value = getattr(args, field)
    if value is not None:
      row[field] = value
  daci_list_args = {
    "contributors": args.contributor,
    "informed": args.informed,
  }
  for field, value in daci_list_args.items():
    if value is not None:
      row[field] = parse_check(value)
  issues = validate_row(root, row, ledger=temp_ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  target_rows.append({
    "id": target_id,
    "title": target_title,
    "owner": owner,
    "status": "active",
    "review_cadence": args.review_cadence,
    "check": checks[0],
  })
  rows.append(row)
  write_target_rows(root, target_rows)
  write_rows(root, rows)
  print(f"activated {idea_id} from {lesson.get('id')} target={target_id}")
  return 0


def cmd_lessons(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  learning_rows = load_learning_ledger_rows(root)
  issues = learning_ledger_freshness_issues(rows, ledger, learning_rows)
  if issues:
    raise SystemExit("\n".join(issues))
  filtered = filter_learning_rows(
    learning_rows,
    facet=args.facet,
    target=args.target,
    check=args.check,
    artifact=args.artifact,
  )
  if args.json:
    print(json.dumps({"lessons": filtered}, sort_keys=True))
    return 0
  if not filtered:
    print("lessons: none")
    return 0
  for row in filtered:
    print(
      f"{row.get('id')}: target={row.get('target_id')} facet={row.get('facet')} "
      f"check={row.get('check')}"
    )
    print(f"  {row.get('lesson', '')}")
    follow_up = row.get("follow_up")
    if isinstance(follow_up, str) and follow_up:
      print(f"  follow_up: {follow_up}")
  return 0


def cmd_ready(root: pathlib.Path, args: argparse.Namespace) -> int:
  del args
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  ready = ready_rows(rows)
  blocked = [
    (row, readiness_blockers(row))
    for row in rows
    if row.get("state") in QUEUE_READY_STATES and not is_queue_ready(row)
  ]
  conflicts = ready_conflicts(rows)
  batch = recommended_ready_batch(rows)
  if not ready:
    print("ready: none")
  for row in ready:
    print(f"{row['id']}: {row.get('title', '')}{ready_suffix(row)}")
  for row, blockers in blocked:
    print(f"blocked: {row.get('id')}: {', '.join(blockers)}")
  if conflicts:
    for left, right, overlaps in conflicts:
      print(
        f"conflict: {left.get('id')} <-> {right.get('id')}: "
        + ", ".join(overlaps)
      )
  else:
    print("conflicts: none")
  if batch:
    print("recommended_batch: " + ", ".join(str(row.get("id")) for row in batch))
  else:
    print("recommended_batch: none")
  return 0


def cmd_report(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  issues = validate_rows(root, rows, ledger=ledger)
  now = datetime.now(timezone.utc)
  stale: list[dict[str, object]] = []
  for row in rows:
    if row.get("state") not in {"seed", "shaped", "decided"}:
      continue
    updated = row.get("updated_at") or row.get("created_at")
    if not isinstance(updated, str):
      stale.append(row)
      continue
    try:
      age = now - datetime.fromisoformat(updated)
    except ValueError:
      stale.append(row)
      continue
    if age.days >= args.stale_days:
      stale.append(row)
  blocked = blocked_decision_rows(rows)
  unreviewed = unreviewed_done_rows(rows)
  target_lines = target_summary_rows(rows, ledger, now=now)
  unused_targets = unused_active_targets(rows, ledger)
  learning_rows = load_learning_ledger_rows(root)
  issues.extend(learning_ledger_freshness_issues(rows, ledger, learning_rows))
  candidate = next_bet_candidate(
    rows,
    ledger,
    learning_rows if learning_ledger_path(root).is_file() else None,
  )
  print(f"ideas: {len(rows)}")
  print(f"validation_issues: {len(issues)}")
  print(f"stale: {len(stale)}")
  print(f"blocked_decisions: {len(blocked)}")
  print(f"targets: {len(ledger.ordered)}")
  print(f"learning_ledger_rows: {len(learning_rows)}")
  print(f"unused_active_targets: {len(unused_targets)}")
  print(f"done_without_review: {len(unreviewed)}")
  for issue in issues:
    print(f"  issue: {issue}")
  for row in stale:
    print(f"  stale: {row.get('id')} state={row.get('state')}")
  for row in blocked:
    print(
      f"  blocked_decision: {row.get('id')} owner={row.get('owner')} "
      f"state={row.get('state')}"
    )
  for target_line in target_lines:
    print(f"  target: {target_line}")
  for target_id in unused_targets:
    print(f"  unused_target: {target_id}")
  for row in unreviewed:
    print(f"  unreviewed_done: {row.get('id')}")
  for row in learning_rows[:3]:
    print(
      f"  learning_lesson: {row.get('id')} target={row.get('target_id')} "
      f"facet={row.get('facet')} check={row.get('check')}"
    )
  if candidate is not None:
    print(
      "next_bet_candidate: "
      f"source={candidate['source_id']} target={candidate['source_target']} "
      f"owner={candidate['owner']} score={candidate['score']} "
      f"reviewed_at={candidate['reviewed_at']} check={candidate.get('check', '')} "
      f"action={candidate['action']}"
    )
    if candidate.get("lesson"):
      print(
        "  next_bet_evidence: "
        f"artifact={candidate.get('source_artifact', '')} "
        f"lesson={candidate['lesson']}"
      )
  print("evidence_lineage:")
  lineage_count = 0
  for row in rows:
    idea_id = row.get("id")
    source_lesson = row.get("source_lesson")
    source_check = row.get("source_check")
    source_artifact = row.get("source_artifact")
    reviewed_by = row.get("reviewed_by")
    reviewed_at = row.get("reviewed_at")
    if any([source_lesson, source_check, source_artifact, reviewed_by, reviewed_at]):
      lineage_parts = []
      if source_lesson:
        lineage_parts.append(f"lesson={source_lesson}")
      if source_check:
        lineage_parts.append(f"check={source_check}")
      if source_artifact:
        lineage_parts.append(f"artifact={source_artifact}")
      if reviewed_by:
        lineage_parts.append(f"reviewed_by={reviewed_by}")
      if reviewed_at:
        lineage_parts.append(f"reviewed_at={reviewed_at}")
      if lineage_parts:
        print(f"  {idea_id}: {' '.join(lineage_parts)}")
        lineage_count += 1
  if lineage_count == 0:
    print("  - none")
  if args.cost:
    risky = cost_risk_rows(rows)
    print(f"cost_risks: {len(risky)}")
    for row, reasons in risky:
      print(f"  cost_risk: {row.get('id')} {' '.join(reasons)}")
    budgets = facet_budgets(root)
    print(f"facet_budgets: {len(budgets)}")
    for budget in budgets:
      print(
        f"  facet_budget: {budget.name} owns={budget.owns} "
        f"consider={budget.considerations} commands={budget.commands} "
        f"checks={budget.checks} closeout={budget.closeout_checks} docs={budget.docs}"
      )
  return 1 if issues else 0


def cmd_sync_learning_ledger(root: pathlib.Path, args: argparse.Namespace) -> int:
  del args
  rows = load_rows(root)
  ledger = load_target_ledger(root)
  issues = validate_rows(root, rows, ledger=ledger)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  derived = derive_learning_ledger_rows(rows, ledger)
  write_learning_ledger_rows(root, derived)
  print(f"sync_learning_ledger: {len(derived)} rows")
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="ideas")
  parser.add_argument("--root", default=os.environ.get("REPO_ROOT") or os.getcwd())
  sub = parser.add_subparsers(dest="cmd", required=True)

  p_list = sub.add_parser("list")
  p_list.add_argument("--state", choices=STATES)
  p_list.add_argument("--owner")
  p_list.add_argument("--json", action="store_true")
  p_list.set_defaults(func=cmd_list)

  p_add = sub.add_parser("add")
  p_add.add_argument("--id", required=True)
  p_add.add_argument("--title", required=True)
  p_add.add_argument("--owner", required=True)
  p_add.add_argument("--target", required=True)
  p_add.add_argument("--effect", required=True)
  p_add.add_argument("--check", action="append", required=True)
  p_add.add_argument("--reversibility", required=True)
  p_add.add_argument("--maintenance", choices=SCORES, required=True)
  p_add.add_argument("--go-live-cost", dest="go_live_cost", choices=SCORES)
  p_add.add_argument("--maintenance-overhead", choices=SCORES)
  p_add.add_argument("--check-cost", choices=SCORES)
  p_add.add_argument("--tool-sprawl", choices=SCORES)
  p_add.add_argument("--driver")
  p_add.add_argument("--approver")
  p_add.add_argument("--contributor", action="append")
  p_add.add_argument("--informed", action="append")
  p_add.add_argument("--parallel-mode", choices=PARALLEL_MODES)
  p_add.add_argument("--worktree", choices=WORKTREE_MODES)
  p_add.add_argument("--write-scope", action="append")
  p_add.add_argument("--state", choices=STATES, default="seed")
  p_add.add_argument("--decision-required", action="store_true")
  p_add.add_argument("--notes")
  p_add.set_defaults(func=cmd_add)

  p_score = sub.add_parser("score")
  p_score.add_argument("id")
  p_score.add_argument("--return", dest="return_score", choices=SCORES, required=True)
  p_score.add_argument("--time-sink", choices=SCORES, required=True)
  p_score.add_argument("--go-live", choices=SCORES, required=True)
  p_score.add_argument("--maintenance", dest="maintenance_score", choices=SCORES, required=True)
  p_score.add_argument("--reversibility", dest="reversibility_score", choices=SCORES, required=True)
  p_score.add_argument("--fit", choices=SCORES, required=True)
  p_score.add_argument("--verdict", choices=VERDICTS, required=True)
  p_score.add_argument("--cost-estimate", dest="cost_estimate", type=float, help="Cost estimate in days or hours")
  p_score.set_defaults(func=cmd_score)

  p_promote = sub.add_parser("promote")
  p_promote.add_argument("id")
  p_promote.add_argument("--state", choices=STATES, required=True)
  p_promote.set_defaults(func=cmd_promote)

  p_shape = sub.add_parser("shape_from_decision")
  p_shape.add_argument("--id", required=True)
  p_shape.add_argument("--title", required=True)
  p_shape.add_argument("--recommendation", required=True)
  p_shape.add_argument("--target", required=True)
  p_shape.add_argument("--owner")
  p_shape.add_argument("--link")
  p_shape.set_defaults(func=cmd_shape_from_decision)

  p_park = sub.add_parser("park")
  p_park.add_argument("id")
  p_park.add_argument("--reason", required=True)
  p_park.set_defaults(func=cmd_park)

  p_review = sub.add_parser("review")
  p_review.add_argument("id")
  p_review.add_argument("--expected", required=True)
  p_review.add_argument("--actual", required=True)
  p_review.add_argument("--follow-up")
  p_review.set_defaults(func=cmd_review)

  p_ready = sub.add_parser("ready")
  p_ready.set_defaults(func=cmd_ready)

  p_lessons = sub.add_parser("lessons")
  p_lessons.add_argument("--facet")
  p_lessons.add_argument("--target")
  p_lessons.add_argument("--check")
  p_lessons.add_argument("--artifact")
  p_lessons.add_argument("--json", action="store_true")
  p_lessons.set_defaults(func=cmd_lessons)

  p_report = sub.add_parser("report")
  p_report.add_argument("--stale-days", type=int, default=30)
  p_report.add_argument("--cost", action="store_true")
  p_report.set_defaults(func=cmd_report)

  p_sync_learning = sub.add_parser("sync_learning_ledger")
  p_sync_learning.set_defaults(func=cmd_sync_learning_ledger)

  p_activate_dry_run = sub.add_parser("activate_dry_run")
  p_activate_dry_run.add_argument("target_id")
  p_activate_dry_run.set_defaults(func=cmd_activate_dry_run)

  p_activate_cmd = sub.add_parser("activate")
  p_activate_cmd.add_argument("--target", required=True)
  p_activate_cmd.set_defaults(func=cmd_activate)

  p_archive = sub.add_parser("archive")
  p_archive.add_argument("target_id")
  p_archive.add_argument("--outcome", choices=["pass", "fail"], required=True)
  p_archive.set_defaults(func=cmd_archive)

  p_activate = sub.add_parser("activate_next_bet")

  p_activate.add_argument("--lesson-id")
  p_activate.add_argument("--facet")
  p_activate.add_argument("--target")
  p_activate.add_argument("--check-filter")
  p_activate.add_argument("--artifact")
  p_activate.add_argument("--target-id")
  p_activate.add_argument("--target-title")
  p_activate.add_argument("--idea-id")
  p_activate.add_argument("--idea-title")
  p_activate.add_argument("--effect")
  p_activate.add_argument("--owner")
  p_activate.add_argument("--check", action="append")
  p_activate.add_argument("--review-cadence", default="weekly")
  p_activate.add_argument("--reversibility", default="high")
  p_activate.add_argument("--maintenance", choices=SCORES, default="L")
  p_activate.add_argument("--go-live-cost", dest="go_live_cost", choices=SCORES, default="L")
  p_activate.add_argument("--maintenance-overhead", default="L", choices=SCORES)
  p_activate.add_argument("--check-cost", default="L", choices=SCORES)
  p_activate.add_argument("--tool-sprawl", default="L", choices=SCORES)
  p_activate.add_argument("--driver")
  p_activate.add_argument("--approver")
  p_activate.add_argument("--contributor", action="append")
  p_activate.add_argument("--informed", action="append")
  p_activate.add_argument("--parallel-mode", choices=PARALLEL_MODES, default="serial")
  p_activate.add_argument("--worktree", choices=WORKTREE_MODES, default="required")
  p_activate.add_argument("--write-scope", action="append")
  p_activate.add_argument("--state", choices=QUEUE_READY_STATES, default="shaped")
  p_activate.add_argument("--cost-estimate", dest="cost_estimate", type=float, help="Cost estimate in days or hours")
  p_activate.add_argument("--notes")
  p_activate.set_defaults(func=cmd_activate_next_bet)
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  root = pathlib.Path(args.root).resolve()
  return int(args.func(root, args))


if __name__ == "__main__":
  raise SystemExit(main())
