"""`personality clear <name>` — wipe `.local/personalities/<name>/` state.

Definitions under `.agents/personalities/<name>/` are NEVER touched.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Sequence

from tools.personality_pkg import definitions, state


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="personality clear")
  p.add_argument("name")
  p.add_argument("--force", action="store_true",
                 help="skip diagnostic checks; never deletes the definition")
  p.add_argument("--lock-mode", choices=("fail", "wait"), default="fail")
  p.add_argument("--lock-timeout", type=float, default=300.0)
  return p


def run(args: argparse.Namespace, *, repo_root: pathlib.Path,
        out=sys.stdout, err=sys.stderr) -> int:
  # Validate the personality exists (so we don't silently `clear` a typo).
  try:
    definitions.load_personality(repo_root, args.name)
  except definitions.DefinitionError as exc:
    err.write(f"personality clear: {exc}\n")
    return 2
  d = state.state_dir(repo_root, args.name)
  if not d.exists():
    out.write(f"personality clear: no state for {args.name!r}; nothing to do\n")
    return 0
  try:
    with state.acquire_lock(
      repo_root, args.name,
      mode="clear",
      command=f"personality clear {args.name}",
      lock_mode=args.lock_mode,
      timeout=args.lock_timeout,
    ):
      removed = state.clear_state(repo_root, args.name)
  except state.LockBusy as exc:
    err.write(f"personality clear: lock busy: {exc}\n")
    return 3
  except state.LockTimeout as exc:
    err.write(f"personality clear: lock timeout: {exc}\n")
    return 3
  if removed:
    out.write(f"personality clear: removed state for {args.name!r}\n")
  return 0


def main(argv: Sequence[str] | None, *, repo_root: pathlib.Path) -> int:
  args = build_parser().parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
