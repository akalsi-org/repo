"""`infra vxlan-up` and `infra hosts-render` subcommand handlers.

Caveman style on user-facing strings. Idempotent: re-running vxlan-up
on a host re-renders config + restarts the unit but does NOT regenerate
inventory state. Static peer list (issue #5); gossip is #6.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Sequence

from tools.infra_pkg import inventory, ssh, units_render, vxlan, wg


def _err(msg: str) -> None:
  print(f"infra: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
  print(f"infra: {msg}")


# --- shared helpers ---------------------------------------------------


def _find_host(data: dict, *, ssh_target: str) -> dict:
  for h in data.get("hosts", []):
    if h.get("ssh_target") == ssh_target:
      return h
  raise SystemExit(
    f"infra: no adopted host with ssh_target {ssh_target!r}; run infra adopt first"
  )


def _peer_table_from_host(host: dict) -> list[dict]:
  raw = host.get("peers")
  if raw is None:
    return []
  if not isinstance(raw, list):
    raise SystemExit(
      f"infra: host peers field has bad shape {type(raw).__name__}; want list"
    )
  return [p for p in raw if isinstance(p, dict)]


def _full_peer_table(host: dict) -> list[dict]:
  """Return self + foreign peers as a unified peer table.

  /etc/hosts wants self too: each node should resolve its own
  `node-<id>.c<cluster>`. The FDB rendering excludes self via
  `self_node_id`.
  """
  self_entry = {
    "cluster_id": int(host["cluster_id"]),
    "node_id": int(host["node_id"]),
  }
  out = [self_entry] + _peer_table_from_host(host)
  # Dedup by (cluster_id, node_id), keep first.
  seen: set[tuple[int, int]] = set()
  uniq: list[dict] = []
  for p in out:
    key = (int(p.get("cluster_id", 0)), int(p.get("node_id", 0)))
    if key in seen:
      continue
    seen.add(key)
    uniq.append(p)
  return uniq


def _ensure_vxlan_fields(host: dict) -> None:
  """Schema migration: existing host records get VXLAN fields populated lazily."""
  host.setdefault("inner_mtu", vxlan.DEFAULT_INNER_MTU)
  host.setdefault("vxlan_dstport", vxlan.DEFAULT_DSTPORT)


def _install_vxlan_unit(
  ssh_target: str,
  sudo_word: str,
  runner,
  cluster_id: int,
  execstart_block: str,
) -> None:
  body = units_render.render_template(
    vxlan.VXLAN_UNIT_TEMPLATE,
    {
      "CLUSTER_ID": str(cluster_id),
      "EXECSTART_BLOCK": execstart_block,
    },
  )
  res = ssh.scp_write(
    ssh_target, vxlan.VXLAN_UNIT_INSTALL_PATH, body,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if res.rc != 0:
    raise SystemExit(
      f"infra: vxlan unit write failed: {res.stderr.strip() or res.rc}"
    )
  res = ssh.ssh_run(
    ssh_target, "systemctl daemon-reload",
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if res.rc != 0:
    raise SystemExit(
      f"infra: systemctl daemon-reload failed: {res.stderr.strip() or res.rc}"
    )


def _enable_and_restart_vxlan(
  ssh_target: str, sudo_word: str, runner, cluster_id: int,
) -> None:
  unit = f"vxlan-overlay@{cluster_id}.service"
  cmd = (
    f"systemctl enable {unit}; "
    f"systemctl restart {unit}"
  )
  res = ssh.ssh_run(ssh_target, cmd, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: vxlan unit enable/restart failed: {res.stderr.strip() or res.rc}"
    )


# --- vxlan-up ---------------------------------------------------------


def _vxlan_up_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra vxlan-up",
    description="Bring up VXLAN overlay on top of WG underlay (ADR-0014).",
  )
  p.add_argument("ssh_target", help="user@host or alias of an adopted host")
  p.add_argument(
    "--mtu", type=int, default=None,
    help=f"override inner MTU (default {vxlan.DEFAULT_INNER_MTU})",
  )
  p.add_argument(
    "--dstport", type=int, default=None,
    help=f"override VXLAN UDP dstport (default {vxlan.DEFAULT_DSTPORT})",
  )
  p.add_argument(
    "--dry-run", action="store_true",
    help="print actions but issue no SSH commands",
  )
  return p


def vxlan_up_run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner: ssh.Runner | None = None,
) -> int:
  runner = runner or ssh._default_runner
  data = inventory.load(repo_root)
  host = _find_host(data, ssh_target=args.ssh_target)
  cluster_id = int(host["cluster_id"])
  node_id = int(host["node_id"])

  _ensure_vxlan_fields(host)
  if not host.get("wg_pubkey"):
    raise SystemExit(
      f"infra: {args.ssh_target} has no WG state; run infra wg-up first"
    )
  mtu = int(args.mtu if args.mtu is not None else host.get("inner_mtu") or vxlan.DEFAULT_INNER_MTU)
  dstport = int(
    args.dstport if args.dstport is not None
    else host.get("vxlan_dstport") or vxlan.DEFAULT_DSTPORT
  )

  wg_dev = wg.interface_name(cluster_id)
  peer_table = _peer_table_from_host(host)
  ip_link_argv = vxlan.render_ip_link_args(
    cluster_id, wg_dev, dstport=dstport, mtu=mtu,
  )
  fdb_argv_list = vxlan.render_fdb_appends(cluster_id, peer_table, node_id)
  execstart_lines = vxlan.render_unit_execstart_lines(
    cluster_id=cluster_id,
    wg_dev_name=wg_dev,
    peer_table=peer_table,
    self_node_id=node_id,
    dstport=dstport,
    mtu=mtu,
  )

  if args.dry_run:
    _ok(f"dry-run: vxlan-up cluster={cluster_id} node={node_id} mtu={mtu} dstport={dstport}")
    _ok(f"dry-run: ip link argv: {' '.join(ip_link_argv)}")
    _ok(f"dry-run: {len(fdb_argv_list)} fdb append(s)")
    return 0

  sudo_word = ssh.probe_root_or_sudo(args.ssh_target, runner=runner)
  _ok(f"ssh: {args.ssh_target} reachable as {sudo_word}")

  vxlan.apply_vxlan(
    args.ssh_target, cluster_id, ip_link_argv, fdb_argv_list,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  _ok(f"vxlan: applied vxlan-c{cluster_id} ({len(fdb_argv_list)} peer(s))")

  block = vxlan.render_etc_hosts_block(cluster_id, _full_peer_table(host))
  vxlan.update_etc_hosts(
    args.ssh_target, cluster_id, block,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  _ok(f"hosts: rendered /etc/hosts block c{cluster_id}")

  execstart_block = "\n".join(execstart_lines)
  _install_vxlan_unit(
    args.ssh_target, sudo_word, runner, cluster_id, execstart_block,
  )
  _enable_and_restart_vxlan(args.ssh_target, sudo_word, runner, cluster_id)
  _ok(f"vxlan: enabled vxlan-overlay@{cluster_id}.service")

  host["inner_mtu"] = mtu
  host["vxlan_dstport"] = dstport
  inventory.upsert(repo_root, host)
  _ok(f"inventory: updated vxlan state for {args.ssh_target}")
  return 0


def vxlan_up_main(
  argv: Sequence[str] | None,
  *,
  repo_root: pathlib.Path,
) -> int:
  parser = _vxlan_up_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return vxlan_up_run(args, repo_root=repo_root)


# --- hosts-render -----------------------------------------------------


def _hosts_render_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra hosts-render",
    description="Re-render /etc/hosts block from current peer table.",
  )
  p.add_argument("ssh_target", help="user@host or alias of an adopted host")
  p.add_argument(
    "--dry-run", action="store_true",
    help="print actions but issue no SSH commands",
  )
  return p


def hosts_render_run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner: ssh.Runner | None = None,
) -> int:
  runner = runner or ssh._default_runner
  data = inventory.load(repo_root)
  host = _find_host(data, ssh_target=args.ssh_target)
  cluster_id = int(host["cluster_id"])
  block = vxlan.render_etc_hosts_block(cluster_id, _full_peer_table(host))

  if args.dry_run:
    _ok(f"dry-run: hosts-render cluster={cluster_id}")
    sys.stdout.write(block)
    return 0

  sudo_word = ssh.probe_root_or_sudo(args.ssh_target, runner=runner)
  vxlan.update_etc_hosts(
    args.ssh_target, cluster_id, block,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  _ok(f"hosts: rendered /etc/hosts block c{cluster_id} on {args.ssh_target}")
  return 0


def hosts_render_main(
  argv: Sequence[str] | None,
  *,
  repo_root: pathlib.Path,
) -> int:
  parser = _hosts_render_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return hosts_render_run(args, repo_root=repo_root)
