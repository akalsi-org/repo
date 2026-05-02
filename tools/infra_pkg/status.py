"""`infra status` — list adopted hosts from .local/infra/inventory.json."""
from __future__ import annotations

import argparse
import pathlib
from typing import Sequence

from tools.infra_pkg import inventory, ssh


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="infra status")
  p.add_argument("--probe", action="store_true",
                 help="ssh-probe each host to refresh last_reachable")
  return p


def _probe(host: dict, runner=None) -> bool:
  runner = runner or ssh._default_runner
  res = ssh.ssh_run(host["ssh_target"], "true", runner=runner)
  return res.rc == 0


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner=None,
) -> int:
  data = inventory.load(repo_root)
  hosts = data["hosts"]
  if not hosts:
    print("infra: no adopted hosts in .local/infra/inventory.json")
    return 0
  changed = False
  for host in hosts:
    if args.probe:
      reachable = _probe(host, runner=runner)
      host["last_reachable"] = reachable
      host["last_reachable_at"] = inventory.now_iso()
      changed = True
  if changed:
    inventory.save(repo_root, data)
  for host in hosts:
    state = "?" if host.get("last_reachable") in (None, "") else (
      "up" if host["last_reachable"] else "down"
    )
    print(
      f"cluster={host.get('cluster_id')} node={host.get('node_id')} "
      f"target={host.get('ssh_target')} provider={host.get('provider_label')} "
      f"arch={host.get('arch','?')} smt={host.get('smt_state','?')} "
      f"last_reachable={state} at={host.get('last_reachable_at','?')}"
    )
  return 0


def main(argv: Sequence[str] | None = None, *, repo_root: pathlib.Path) -> int:
  parser = build_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
