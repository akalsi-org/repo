"""`personality list` — show roster + last-active timestamp."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, TextIO, Sequence

from tools.personality_pkg import definitions, state


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="personality list")
  p.add_argument("--json", action="store_true", help="emit JSON instead of plain text")
  p.add_argument("--state", action="store_true",
                 help="include state-only fields (last_active, has_session)")
  return p


def collect_rows(repo_root: pathlib.Path) -> list[dict[str, Any]]:
  defaults = definitions.load_defaults(repo_root)
  rows: list[dict[str, Any]] = []
  for name in definitions.list_personalities(repo_root):
    p = definitions.load_personality(repo_root, name)
    cfg = definitions.resolve_effective(defaults, p)
    sid = state.read_session_id(repo_root, name)
    last = state.last_active_iso(repo_root, name)
    rows.append({
      "name": p.name,
      "title": p.title,
      "cli": p.cli,
      "model": cfg.model,
      "effort": cfg.effort,
      "has_session": bool(sid),
      "last_active": last or "never",
      "delegates_to": list(p.delegates_to),
    })
  return rows


def run(args: argparse.Namespace, *, repo_root: pathlib.Path,
        out: TextIO = sys.stdout) -> int:
  rows = collect_rows(repo_root)
  if args.json:
    out.write(json.dumps(rows, indent=2) + "\n")
    return 0
  if not rows:
    out.write("personality: no personalities defined under .agents/personalities/\n")
    return 0
  for row in rows:
    out.write(
      f"{row['name']:14} title={row['title']!r:18} "
      f"cli={row['cli']:7} model={row['model']:24} "
      f"effort={str(row['effort']):6} last_active={row['last_active']}\n"
    )
  return 0


def main(argv: Sequence[str] | None, *, repo_root: pathlib.Path) -> int:
  args = build_parser().parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
