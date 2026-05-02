"""`infra wg-up` and `infra wg-peer-add` subcommand handlers.

Caveman style on user-facing strings. Idempotent: re-running wg-up
on an adopted host re-renders the config and restarts the unit but
does NOT regenerate the keypair if one already exists.

Static peer list for this slice (issue #4). Gossip auto-reconcile is
issue #6.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Sequence

from tools.infra_pkg import inventory, ssh, units_render, wg


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


def _peers_for_cluster(data: dict, cluster_id: int) -> list[dict]:
  return [
    h for h in data.get("hosts", [])
    if int(h.get("cluster_id", 0)) == cluster_id
  ]


def _peer_table_from_host(host: dict) -> list[dict]:
  """Return host['peers'] as a list of dicts; default to []."""
  raw = host.get("peers")
  if raw is None:
    return []
  if not isinstance(raw, list):
    raise SystemExit(
      f"infra: host peers field has bad shape {type(raw).__name__}; want list"
    )
  return [p for p in raw if isinstance(p, dict)]


def _ensure_wg_fields(host: dict) -> None:
  """Schema migration: existing host records get WG fields populated lazily."""
  host.setdefault("wg_pubkey", "")
  host.setdefault("wg_underlay_endpoint", "")
  host.setdefault("wg_listen_port", wg.DEFAULT_LISTEN_PORT)
  host.setdefault("peers", [])


def _install_wg_unit(
  ssh_target: str, sudo_word: str, runner, cluster_id: int,
) -> None:
  """Render and install the wg-overlay@.service template; daemon-reload."""
  body = units_render.render_template(
    wg.WG_UNIT_TEMPLATE, {"CLUSTER_ID": str(cluster_id)},
  )
  res = ssh.scp_write(
    ssh_target, wg.WG_UNIT_INSTALL_PATH, body,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if res.rc != 0:
    raise SystemExit(
      f"infra: wg unit write failed: {res.stderr.strip() or res.rc}"
    )
  res = ssh.ssh_run(
    ssh_target, "systemctl daemon-reload",
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if res.rc != 0:
    raise SystemExit(
      f"infra: systemctl daemon-reload failed: {res.stderr.strip() or res.rc}"
    )


def _enable_and_restart_wg(
  ssh_target: str, sudo_word: str, runner, cluster_id: int,
) -> None:
  unit = f"wg-overlay@{cluster_id}.service"
  cmd = (
    f"systemctl enable {unit}; "
    f"systemctl restart {unit}"
  )
  res = ssh.ssh_run(ssh_target, cmd, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: wg unit enable/restart failed: {res.stderr.strip() or res.rc}"
    )


# --- wg-up ------------------------------------------------------------


def _wg_up_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra wg-up",
    description="Bring up WireGuard underlay on an adopted host (ADR-0014).",
  )
  p.add_argument("ssh_target", help="user@host or alias of an adopted host")
  p.add_argument(
    "--listen-port", type=int, default=None,
    help=f"override WG listen port (default {wg.DEFAULT_LISTEN_PORT})",
  )
  p.add_argument(
    "--endpoint", default=None, metavar="HOST:PORT",
    help="public underlay endpoint advertised to peers; default ssh_target host plus listen-port",
  )
  p.add_argument(
    "--dry-run", action="store_true",
    help="print actions but issue no SSH commands",
  )
  return p


def _default_endpoint(ssh_target: str, listen_port: int) -> str:
  """Strip user@ from ssh_target and append :port."""
  host = ssh_target.split("@", 1)[-1]
  # Drop any explicit ssh port override "host:22" — wg endpoint is its own port.
  if host.count(":") == 1 and not host.startswith("["):
    host = host.split(":", 1)[0]
  return f"{host}:{listen_port}"


def wg_up_run(
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

  _ensure_wg_fields(host)
  listen_port = (
    int(args.listen_port) if args.listen_port is not None
    else int(host.get("wg_listen_port") or wg.DEFAULT_LISTEN_PORT)
  )
  endpoint = (
    args.endpoint.strip() if args.endpoint
    else (host.get("wg_underlay_endpoint") or _default_endpoint(args.ssh_target, listen_port))
  )

  if args.dry_run:
    _ok(f"dry-run: wg-up cluster={cluster_id} node={node_id} listen={listen_port}")
    _ok(f"dry-run: endpoint would be {endpoint}")
    return 0

  sudo_word = ssh.probe_root_or_sudo(args.ssh_target, runner=runner)
  _ok(f"ssh: {args.ssh_target} reachable as {sudo_word}")

  _, pub_str = wg.generate_keypair(
    cluster_id, args.ssh_target,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  _ok(f"wg: pubkey {pub_str}")

  host["wg_pubkey"] = pub_str
  host["wg_underlay_endpoint"] = endpoint
  host["wg_listen_port"] = listen_port

  # Render config from peers we know about for this cluster, excluding self.
  peer_table = _peer_table_from_host(host)
  config = wg.render_wg_config(
    cluster_id=cluster_id,
    node_id=node_id,
    peer_table=peer_table,
    listen_port=listen_port,
  )
  wg.apply_wg_config(
    args.ssh_target, cluster_id, config,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  _ok(f"wg: wrote {wg.conf_path(cluster_id)} ({len(peer_table)} peer(s))")

  _install_wg_unit(args.ssh_target, sudo_word, runner, cluster_id)
  _enable_and_restart_wg(args.ssh_target, sudo_word, runner, cluster_id)
  _ok(f"wg: enabled wg-overlay@{cluster_id}.service")

  inventory.upsert(repo_root, host)
  _ok(f"inventory: updated wg state for {args.ssh_target}")
  return 0


def wg_up_main(
  argv: Sequence[str] | None,
  *,
  repo_root: pathlib.Path,
) -> int:
  parser = _wg_up_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return wg_up_run(args, repo_root=repo_root)


# --- wg-peer-add ------------------------------------------------------


def _wg_peer_add_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra wg-peer-add",
    description="Register two hosts as WG peers and re-render configs.",
  )
  p.add_argument("node_a", help="ssh_target of node A (must be adopted + wg-up)")
  p.add_argument("node_b", help="ssh_target of node B (must be adopted + wg-up)")
  p.add_argument(
    "--dry-run", action="store_true",
    help="print actions but issue no SSH commands",
  )
  return p


def _peer_record_for(host: dict) -> dict:
  return {
    "cluster_id": int(host["cluster_id"]),
    "node_id": int(host["node_id"]),
    "wg_pubkey": str(host.get("wg_pubkey", "")),
    "wg_underlay_endpoint": str(host.get("wg_underlay_endpoint", "")),
  }


def _add_peer_symmetrically(host: dict, peer: dict) -> bool:
  """Insert/replace `peer` in host['peers']. Returns True if changed."""
  peers = list(_peer_table_from_host(host))
  key = (int(peer["cluster_id"]), int(peer["node_id"]))
  changed = True
  for idx, existing in enumerate(peers):
    if (int(existing.get("cluster_id", 0)), int(existing.get("node_id", 0))) == key:
      if existing == peer:
        changed = False
      peers[idx] = peer
      break
  else:
    peers.append(peer)
  peers.sort(key=lambda p: (int(p.get("cluster_id", 0)), int(p.get("node_id", 0))))
  host["peers"] = peers
  return changed


def _re_render_and_restart(
  host: dict, *, runner: ssh.Runner,
) -> None:
  cluster_id = int(host["cluster_id"])
  node_id = int(host["node_id"])
  listen_port = int(host.get("wg_listen_port") or wg.DEFAULT_LISTEN_PORT)
  config = wg.render_wg_config(
    cluster_id=cluster_id,
    node_id=node_id,
    peer_table=_peer_table_from_host(host),
    listen_port=listen_port,
  )
  ssh_target = host["ssh_target"]
  sudo_word = ssh.probe_root_or_sudo(ssh_target, runner=runner)
  wg.apply_wg_config(
    ssh_target, cluster_id, config,
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  unit = f"wg-overlay@{cluster_id}.service"
  res = ssh.ssh_run(
    ssh_target, f"systemctl restart {unit}",
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if res.rc != 0:
    raise SystemExit(
      f"infra: restart {unit} failed on {ssh_target}: {res.stderr.strip() or res.rc}"
    )


def wg_peer_add_run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner: ssh.Runner | None = None,
) -> int:
  runner = runner or ssh._default_runner
  data = inventory.load(repo_root)
  host_a = _find_host(data, ssh_target=args.node_a)
  host_b = _find_host(data, ssh_target=args.node_b)
  if int(host_a["cluster_id"]) != int(host_b["cluster_id"]):
    raise SystemExit(
      f"infra: nodes are in different clusters "
      f"(a={host_a['cluster_id']}, b={host_b['cluster_id']})"
    )
  if int(host_a["node_id"]) == int(host_b["node_id"]):
    raise SystemExit("infra: peer-add needs two distinct node_ids")
  for h in (host_a, host_b):
    _ensure_wg_fields(h)
    if not h.get("wg_pubkey"):
      raise SystemExit(
        f"infra: {h['ssh_target']} has no wg_pubkey; run infra wg-up first"
      )
    if not h.get("wg_underlay_endpoint"):
      raise SystemExit(
        f"infra: {h['ssh_target']} has no wg_underlay_endpoint; run infra wg-up first"
      )

  peer_b = _peer_record_for(host_b)
  peer_a = _peer_record_for(host_a)
  _add_peer_symmetrically(host_a, peer_b)
  _add_peer_symmetrically(host_b, peer_a)

  if args.dry_run:
    _ok(f"dry-run: peers registered in inventory only "
        f"(a={host_a['ssh_target']}, b={host_b['ssh_target']})")
    inventory.upsert(repo_root, host_a)
    inventory.upsert(repo_root, host_b)
    return 0

  _re_render_and_restart(host_a, runner=runner)
  _ok(f"wg: re-rendered + restarted on {host_a['ssh_target']}")
  _re_render_and_restart(host_b, runner=runner)
  _ok(f"wg: re-rendered + restarted on {host_b['ssh_target']}")

  inventory.upsert(repo_root, host_a)
  inventory.upsert(repo_root, host_b)
  _ok("inventory: peer table updated symmetrically")
  return 0


def wg_peer_add_main(
  argv: Sequence[str] | None,
  *,
  repo_root: pathlib.Path,
) -> int:
  parser = _wg_peer_add_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return wg_peer_add_run(args, repo_root=repo_root)
