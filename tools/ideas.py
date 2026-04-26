"""Idea inventory and backlog gate.

Canonical store: `.agents/ideas/ideas.jsonl`.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(os.environ.get("REPO_ROOT") or pathlib.Path.cwd()).resolve()
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.facets import load_facets


IDEAS_REL = ".agents/ideas/ideas.jsonl"
STATES = ("seed", "shaped", "decided", "queued", "active", "done", "rejected", "parked")
SCORES = ("H", "M", "L")
VERDICTS = ("Do now", "Design first", "Watch", "Avoid")
QUEUE_READY_STATES = ("shaped", "decided", "queued")
COST_FIELDS = ("go_live_cost", "maintenance_overhead", "check_cost", "tool_sprawl")
PARALLEL_MODES = ("safe", "serial", "blocked")
WORKTREE_MODES = ("required", "recommended", "optional")


def utc_now() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ideas_path(root: pathlib.Path) -> pathlib.Path:
  return root / IDEAS_REL


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


def facet_keys(root: pathlib.Path) -> set[str]:
  return {facet.key for facet in load_facets(root)}


def validate_row(root: pathlib.Path, row: dict[str, object]) -> list[str]:
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
    issues.append(f"{ident or '<unknown>'}: parallel_mode must be safe, serial, or blocked")
  worktree = row.get("worktree")
  if worktree is not None and worktree not in WORKTREE_MODES:
    issues.append(f"{ident or '<unknown>'}: worktree must be required, recommended, or optional")
  write_scope = row.get("write_scope")
  if write_scope is not None and (
      not isinstance(write_scope, list)
      or not write_scope
      or not all(isinstance(v, str) and v for v in write_scope)
  ):
    issues.append(f"{ident or '<unknown>'}: write_scope must be non-empty list[str]")
  return issues


def validate_rows(root: pathlib.Path, rows: list[dict[str, object]]) -> list[str]:
  issues: list[str] = []
  seen: set[str] = set()
  for row in rows:
    ident = row.get("id")
    if isinstance(ident, str) and ident:
      if ident in seen:
        issues.append(f"duplicate idea id `{ident}`")
      seen.add(ident)
    issues.extend(validate_row(root, row))
  return issues


def find_row(rows: list[dict[str, object]], ident: str) -> dict[str, object]:
  for row in rows:
    if row.get("id") == ident:
      return row
  raise SystemExit(f"unknown idea `{ident}`")


def parse_check(values: list[str]) -> list[str]:
  return list(dict.fromkeys(values))


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
  return f" [{' '.join(parts)}]" if parts else ""


def cmd_list(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  issues = validate_rows(root, rows)
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
  if args.parallel_mode is not None:
    row["parallel_mode"] = args.parallel_mode
  if args.worktree is not None:
    row["worktree"] = args.worktree
  if args.write_scope is not None:
    row["write_scope"] = parse_check(args.write_scope)
  issues = validate_row(root, row)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  rows.append(row)
  write_rows(root, rows)
  print(f"added {args.id}")
  return 0


def cmd_score(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
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
  row["updated_at"] = utc_now()
  write_rows(root, rows)
  print(f"scored {args.id}")
  return 0


def cmd_promote(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  row = find_row(rows, args.id)
  blockers = queue_blockers(row)
  if args.state == "queued" and blockers:
    raise SystemExit(
      "cannot queue: " + ", ".join(blockers)
    )
  row["state"] = args.state
  row["updated_at"] = utc_now()
  write_rows(root, rows)
  print(f"{args.id} -> {args.state}")
  return 0


def cmd_park(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  row = find_row(rows, args.id)
  row["state"] = "parked"
  row["park_reason"] = args.reason
  row["updated_at"] = utc_now()
  write_rows(root, rows)
  print(f"parked {args.id}")
  return 0


def cmd_ready(root: pathlib.Path, args: argparse.Namespace) -> int:
  del args
  rows = load_rows(root)
  issues = validate_rows(root, rows)
  if issues:
    raise SystemExit("idea validation failed:\n" + "\n".join(f"- {v}" for v in issues))
  ready = [row for row in rows if is_queue_ready(row)]
  blocked = [
    (row, readiness_blockers(row))
    for row in rows
    if row.get("state") in QUEUE_READY_STATES and not is_queue_ready(row)
  ]
  if not ready:
    print("ready: none")
  for row in ready:
    print(f"{row['id']}: {row.get('title', '')}{ready_suffix(row)}")
  for row, blockers in blocked:
    print(f"blocked: {row.get('id')}: {', '.join(blockers)}")
  return 0


def cmd_report(root: pathlib.Path, args: argparse.Namespace) -> int:
  rows = load_rows(root)
  issues = validate_rows(root, rows)
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
  print(f"ideas: {len(rows)}")
  print(f"validation_issues: {len(issues)}")
  print(f"stale: {len(stale)}")
  for issue in issues:
    print(f"  issue: {issue}")
  for row in stale:
    print(f"  stale: {row.get('id')} state={row.get('state')}")
  return 1 if issues else 0


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
  p_score.set_defaults(func=cmd_score)

  p_promote = sub.add_parser("promote")
  p_promote.add_argument("id")
  p_promote.add_argument("--state", choices=STATES, required=True)
  p_promote.set_defaults(func=cmd_promote)

  p_park = sub.add_parser("park")
  p_park.add_argument("id")
  p_park.add_argument("--reason", required=True)
  p_park.set_defaults(func=cmd_park)

  p_ready = sub.add_parser("ready")
  p_ready.set_defaults(func=cmd_ready)

  p_report = sub.add_parser("report")
  p_report.add_argument("--stale-days", type=int, default=30)
  p_report.set_defaults(func=cmd_report)
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  root = pathlib.Path(args.root).resolve()
  return int(args.func(root, args))


if __name__ == "__main__":
  raise SystemExit(main())
