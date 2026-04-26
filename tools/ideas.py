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
QUEUE_READY_STATES = ("shaped", "decided")


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
  if row.get("state") not in QUEUE_READY_STATES:
    return False
  if row.get("decision_required") is True:
    return False
  required = ("target", "reversibility")
  if any(not isinstance(row.get(key), str) or not row.get(key) for key in required):
    return False
  checks = row.get("checks", [])
  return isinstance(checks, list) and bool(checks)


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
  if args.state == "queued" and not is_queue_ready(row):
    raise SystemExit(
      "cannot queue: needs state shaped/decided, target, checks, "
      "reversibility, and decision_required=false"
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
  ready = [row for row in rows if is_queue_ready(row)]
  if not ready:
    print("ready: none")
    return 0
  for row in ready:
    print(f"{row['id']}: {row.get('title', '')}")
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
