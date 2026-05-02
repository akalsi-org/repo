"""`personality` verb dispatcher.

Subcommands:
  personality list                            — show roster + last_active
  personality init <name> --cli <cli> [...]   — scaffold a new definition
  personality as-root <name> [...]            — interactive persistent session
  personality ask <name> [--] <prompt>        — one-shot non-interactive ask
  personality clear <name>                    — wipe local state

Caveman style on user-facing strings.
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import Sequence


SUBCOMMANDS = ("list", "init", "as-root", "ask", "clear")


def _repo_root() -> pathlib.Path:
  env = os.environ.get("REPO_ROOT")
  if env:
    return pathlib.Path(env).resolve()
  return pathlib.Path(__file__).resolve().parents[2]


def _usage() -> str:
  return (
    "usage: personality <subcommand> [args...]\n"
    "  list                            — show roster + last_active\n"
    "  init <name> --cli <cli>         — scaffold definition\n"
    "  as-root <name>                  — interactive persistent session\n"
    "  ask <name> [--] <prompt>        — one-shot non-interactive ask\n"
    "  clear <name>                    — wipe local state\n"
  )


def main(argv: Sequence[str] | None = None) -> int:
  args = list(argv) if argv is not None else sys.argv[1:]
  if not args or args[0] in {"-h", "--help", "help"}:
    sys.stderr.write(_usage())
    return 0 if args and args[0] in {"-h", "--help", "help"} else 2
  sub = args[0]
  rest = args[1:]
  if sub not in SUBCOMMANDS:
    sys.stderr.write(f"personality: unknown subcommand {sub!r}\n{_usage()}")
    return 2

  root = _repo_root()
  if str(root) not in sys.path:
    sys.path.insert(0, str(root))

  if sub == "list":
    from tools.personality_pkg.commands.list_cmd import main as list_main
    return list_main(rest, repo_root=root)
  if sub == "init":
    from tools.personality_pkg.commands.init_cmd import main as init_main
    return init_main(rest, repo_root=root)
  if sub == "as-root":
    from tools.personality_pkg.commands.as_root_cmd import main as as_root_main
    return as_root_main(rest, repo_root=root)
  if sub == "ask":
    from tools.personality_pkg.commands.ask_cmd import main as ask_main
    return ask_main(rest, repo_root=root)
  if sub == "clear":
    from tools.personality_pkg.commands.clear_cmd import main as clear_main
    return clear_main(rest, repo_root=root)
  return 2
