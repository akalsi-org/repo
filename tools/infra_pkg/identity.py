"""Cluster/node identity arithmetic (ADR-0014, identity scheme).

Pure functions. No I/O, no network. Easy to unit-test.

Identity contract:
- Cluster ID: u8, 1..255.
- Node ID: u16, 1..65535.
- Overlay IPv4: 10.<cluster>.<node_high>.<node_low>.
- WG underlay IPv4: 10.200.<cluster>.<node_low>/16.
- Hostname: node-<id>.c<cluster>.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeAddrs:
  cluster_id: int
  node_id: int
  overlay_ipv4: str
  underlay_ipv4: str
  hostname: str


def validate_cluster_id(cluster_id: int) -> int:
  if not isinstance(cluster_id, int) or cluster_id < 1 or cluster_id > 255:
    raise ValueError(f"infra: bad cluster_id {cluster_id!r} (want 1..255)")
  return cluster_id


def validate_node_id(node_id: int) -> int:
  if not isinstance(node_id, int) or node_id < 1 or node_id > 65535:
    raise ValueError(f"infra: bad node_id {node_id!r} (want 1..65535)")
  return node_id


def overlay_ipv4(cluster_id: int, node_id: int) -> str:
  validate_cluster_id(cluster_id)
  validate_node_id(node_id)
  high = (node_id >> 8) & 0xFF
  low = node_id & 0xFF
  return f"10.{cluster_id}.{high}.{low}"


def underlay_ipv4(cluster_id: int, node_id: int) -> str:
  validate_cluster_id(cluster_id)
  validate_node_id(node_id)
  low = node_id & 0xFF
  return f"10.200.{cluster_id}.{low}"


def hostname(cluster_id: int, node_id: int) -> str:
  validate_cluster_id(cluster_id)
  validate_node_id(node_id)
  return f"node-{node_id}.c{cluster_id}"


def node_addrs(cluster_id: int, node_id: int) -> NodeAddrs:
  return NodeAddrs(
    cluster_id=validate_cluster_id(cluster_id),
    node_id=validate_node_id(node_id),
    overlay_ipv4=overlay_ipv4(cluster_id, node_id),
    underlay_ipv4=underlay_ipv4(cluster_id, node_id),
    hostname=hostname(cluster_id, node_id),
  )


def render_etc_hosts(peers: list[NodeAddrs]) -> str:
  """Render an /etc/hosts fragment from a peer table.

  Each peer gets two lines: overlay IP and underlay IP both mapping
  to the same hostname. Sorted by node_id for deterministic output.
  """
  lines: list[str] = []
  lines.append("# managed by infra; do not edit by hand")
  for peer in sorted(peers, key=lambda p: (p.cluster_id, p.node_id)):
    lines.append(f"{peer.overlay_ipv4}\t{peer.hostname}")
    lines.append(f"{peer.underlay_ipv4}\t{peer.hostname}-wg")
  lines.append("")
  return "\n".join(lines)
