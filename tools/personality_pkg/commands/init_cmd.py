"""`personality init <name>` — scaffold a new personality definition."""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import TextIO, Sequence

from tools.personality_pkg import definitions


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="personality init")
  p.add_argument("name")
  p.add_argument("--cli", required=True,
                 choices=definitions.SUPPORTED_CLIS)
  p.add_argument("--title", default=None,
                 help="human-readable title; defaults to capitalized <name>")
  p.add_argument("--model", default=None,
                 help="override the CLI default model")
  p.add_argument("--effort", default=None,
                 help="override the CLI default effort")
  p.add_argument("--force", action="store_true",
                 help="overwrite an existing definition")
  return p


TEMPLATE = """\
---
name: {name}
title: {title}
cli: {cli}
model: {model}
effort: {effort}
mode: interactive
delegates_to: []
tools:
  shell_allowlist:
    - "./repo.sh personality ask *"
clear_policy: state-only
---

# {title}

Mission: <describe role mission>.

Authority: <what this role decides on its own>.

Decision posture: <bias for action vs. consensus, etc.>.

Escalation: <when to escalate, to whom>.

Delegation: use `personality ask <name> "<prompt>"` for cross-role
questions. Honor any restrictions listed in `delegates_to`.

Operator note: this body is the personality's voice; not chat with the
operator. Use placeholders such as `<login>` and `<org>` instead of
concrete GitHub identifiers.
"""


def _yaml_scalar(value: object) -> str:
  if value is None:
    return "null"
  if isinstance(value, str):
    return value
  return str(value)


def run(args: argparse.Namespace, *, repo_root: pathlib.Path,
        out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
  if not definitions.SLUG_RE.match(args.name):
    err.write(f"personality init: name {args.name!r} is not a valid slug\n")
    return 2
  base = repo_root / definitions.PERSONALITIES_REL / args.name
  target = base / "personality.md"
  if target.exists() and not args.force:
    err.write(f"personality init: {target.relative_to(repo_root)} exists; use --force to overwrite\n")
    return 2
  base.mkdir(parents=True, exist_ok=True)
  title = args.title or args.name.replace("-", " ").replace("_", " ").title()
  body = TEMPLATE.format(
    name=args.name,
    title=title,
    cli=args.cli,
    model=_yaml_scalar(args.model),
    effort=_yaml_scalar(args.effort),
  )
  target.write_text(body, encoding="utf-8")
  defaults_path = repo_root / definitions.DEFAULTS_REL
  if not defaults_path.exists():
    err.write(
      f"personality init: warning — {definitions.DEFAULTS_REL} missing; "
      "create it before invoking the personality\n"
    )
  out.write(f"personality init: created {target.relative_to(repo_root)}\n")
  return 0


def main(argv: Sequence[str] | None, *, repo_root: pathlib.Path) -> int:
  args = build_parser().parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
