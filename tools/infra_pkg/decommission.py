"""`infra decommission` subcommand."""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from typing import Callable, Sequence

from tools.infra_pkg import inventory


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _provider_script(repo_root: pathlib.Path, provider: str) -> pathlib.Path:
  return repo_root / "bootstrap" / "providers" / f"{provider}.sh"


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra decommission",
    description="Destroy provider VM and remove inventory entry.",
  )
  p.add_argument("provider", choices=("hetzner", "contabo"))
  p.add_argument("vm_id")
  return p


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner: Runner = subprocess.run,
) -> int:
  if args.provider == "contabo":
    print("infra: contabo no API impl; remove host from inventory + power-off via Contabo UI", file=sys.stderr)
    return 1

  proc = runner(
    [str(_provider_script(repo_root, args.provider)), "destroy_vm", args.vm_id],
    text=True,
    capture_output=True,
    check=False,
  )
  if proc.returncode != 0:
    raise SystemExit(f"infra: decommission failed: {proc.stderr.strip() or proc.returncode}")
  _, removed = inventory.remove_by_provider_vm_id(repo_root, args.provider, args.vm_id)
  print(f"infra: decommissioned {args.provider} vm {args.vm_id}; inventory_removed={removed}")
  return 0


def main(argv: Sequence[str] | None = None, *, repo_root: pathlib.Path) -> int:
  parser = build_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
