"""`infra` verb dispatcher entry point.

Subcommands:
  infra adopt              <provider_label> <ssh_target> <cluster_id> <node_id> [seeds...]
  infra status             [--probe]
  infra wg-up              <ssh_target> [--listen-port N] [--endpoint HOST:PORT]
  infra wg-peer-add        <node_a_ssh> <node_b_ssh>
  infra vxlan-up           <ssh_target> [--mtu N] [--dstport N]
  infra hosts-render       <ssh_target>
  infra provision-hetzner  [--arch arm64|amd64] [--region R] [--type T]
  infra decommission       <provider> <vm_id>

Caveman style on user-facing strings.
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import Sequence


def _repo_root() -> pathlib.Path:
  env = os.environ.get("REPO_ROOT")
  if env:
    return pathlib.Path(env).resolve()
  return pathlib.Path(__file__).resolve().parents[2]


SUBCOMMANDS = (
  "adopt", "status", "wg-up", "wg-peer-add", "vxlan-up", "hosts-render",
  "provision-hetzner", "decommission",
)


def _usage() -> str:
  return (
    "usage: infra <subcommand> [args...]\n"
    "  adopt              <provider> <ssh_target> <cluster_id> <node_id> [seeds...]\n"
    "  status             [--probe]\n"
    "  wg-up              <ssh_target> [--listen-port N] [--endpoint HOST:PORT]\n"
    "  wg-peer-add        <node_a_ssh> <node_b_ssh>\n"
    "  vxlan-up           <ssh_target> [--mtu N] [--dstport N]\n"
    "  hosts-render       <ssh_target>\n"
    "  provision-hetzner  [--arch arm64|amd64] [--region R] [--type T]\n"
    "  decommission       <provider> <vm_id>\n"
  )


def main(argv: Sequence[str] | None = None) -> int:
  args = list(argv) if argv is not None else sys.argv[1:]
  if not args or args[0] in {"-h", "--help", "help"}:
    sys.stderr.write(_usage())
    return 0 if args and args[0] in {"-h", "--help", "help"} else 2
  sub = args[0]
  rest = args[1:]
  if sub not in SUBCOMMANDS:
    sys.stderr.write(f"infra: unknown subcommand {sub!r}\n{_usage()}")
    return 2

  root = _repo_root()
  if str(root) not in sys.path:
    sys.path.insert(0, str(root))

  if sub == "adopt":
    from tools.infra_pkg.adopt import main as adopt_main
    return adopt_main(rest, repo_root=root)
  if sub == "status":
    from tools.infra_pkg.status import main as status_main
    return status_main(rest, repo_root=root)
  if sub == "wg-up":
    from tools.infra_pkg.wg_cmd import wg_up_main
    return wg_up_main(rest, repo_root=root)
  if sub == "wg-peer-add":
    from tools.infra_pkg.wg_cmd import wg_peer_add_main
    return wg_peer_add_main(rest, repo_root=root)
  if sub == "vxlan-up":
    from tools.infra_pkg.vxlan_cmd import vxlan_up_main
    return vxlan_up_main(rest, repo_root=root)
  if sub == "hosts-render":
    from tools.infra_pkg.vxlan_cmd import hosts_render_main
    return hosts_render_main(rest, repo_root=root)
  if sub == "provision-hetzner":
    from tools.infra_pkg.provision_hetzner import main as provision_hetzner_main
    return provision_hetzner_main(rest, repo_root=root)
  if sub == "decommission":
    from tools.infra_pkg.decommission import main as decommission_main
    return decommission_main(rest, repo_root=root)
  return 2
