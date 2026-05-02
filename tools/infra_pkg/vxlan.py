"""VXLAN overlay helpers (ADR-0014, issue #5).

Stacks on top of the WG underlay from issue #4. One VNI per cluster
(VNI == cluster_id). The VXLAN device rides ON the WG interface
(`dev wg-c<cluster>`); FDB entries head-end-replicate broadcast to
each peer's WG underlay IPv4. Inner overlay address is
`10.<cluster>.<node_high>.<node_low>/16`. Inner MTU defaults to 1370.

Pure functions where possible. SSH-touching functions accept a runner
so tests mock the wire boundary.

Layout on the host:
- /etc/systemd/system/vxlan-overlay@.service  (rendered from template)
- /etc/hosts                                   (managed BEGIN/END block)

The interface name is `vxlan-c<cluster>`. The systemd unit is
templated as `vxlan-overlay@<cluster>.service` and uses %i in
ExecStart.
"""
from __future__ import annotations

import shlex
from typing import Iterable, Mapping

from tools.infra_pkg import identity, ssh, wg


DEFAULT_DSTPORT = 4789
DEFAULT_INNER_MTU = 1370
BROADCAST_MAC = "00:00:00:00:00:00"
VXLAN_UNIT_TEMPLATE = "vxlan-overlay@.service.in"
VXLAN_UNIT_INSTALL_PATH = "/etc/systemd/system/vxlan-overlay@.service"

ETC_HOSTS_PATH = "/etc/hosts"


def interface_name(cluster_id: int) -> str:
  """Return the VXLAN interface name for `cluster_id`."""
  identity.validate_cluster_id(cluster_id)
  return f"vxlan-c{cluster_id}"


def inner_ipv4(cluster_id: int, node_id: int) -> str:
  """Return the inner overlay IPv4 (no /mask).

  `10.<cluster>.<node_high>.<node_low>` per ADR-0014 identity scheme.
  """
  return identity.overlay_ipv4(cluster_id, node_id)


def inner_subnet(cluster_id: int) -> str:
  """Return the inner /16 subnet for `cluster_id`."""
  identity.validate_cluster_id(cluster_id)
  return f"10.{cluster_id}.0.0/16"


def hosts_begin_marker(cluster_id: int) -> str:
  identity.validate_cluster_id(cluster_id)
  return f"# BEGIN core-infra c{cluster_id}"


def hosts_end_marker(cluster_id: int) -> str:
  identity.validate_cluster_id(cluster_id)
  return f"# END core-infra c{cluster_id}"


def render_ip_link_args(
  cluster_id: int,
  wg_dev_name: str,
  dstport: int = DEFAULT_DSTPORT,
  mtu: int = DEFAULT_INNER_MTU,
) -> list[str]:
  """Pure: render the `ip link add` argv for the VXLAN device.

  Mirrors:
    ip link add vxlan-c<cluster> type vxlan id <cluster> \
        dev <wg_dev_name> dstport <port> nolearning mtu <mtu>

  Returns a list[str] argv (no `sudo`, no shell quoting).
  """
  identity.validate_cluster_id(cluster_id)
  if not wg_dev_name or not isinstance(wg_dev_name, str):
    raise ValueError(f"infra: bad wg_dev_name {wg_dev_name!r}")
  if not isinstance(dstport, int) or dstport < 1 or dstport > 65535:
    raise ValueError(f"infra: bad dstport {dstport!r}")
  if not isinstance(mtu, int) or mtu < 576 or mtu > 9000:
    raise ValueError(f"infra: bad mtu {mtu!r}")
  iface = interface_name(cluster_id)
  return [
    "ip", "link", "add", iface,
    "type", "vxlan",
    "id", str(cluster_id),
    "dev", wg_dev_name,
    "dstport", str(dstport),
    "nolearning",
    "mtu", str(mtu),
  ]


def render_fdb_appends(
  cluster_id: int,
  peer_table: Iterable[Mapping[str, object]],
  self_node_id: int,
) -> list[list[str]]:
  """Pure: render head-end FDB append argv for each peer (excluding self).

  One `bridge fdb append 00:00:00:00:00:00 dev <iface> dst <peer-wg-ip>`
  argv per peer. The peer underlay IPv4 is computed from
  identity.underlay_ipv4(cluster_id, peer_node_id) — never trusts any
  externally-provided dst literal.
  """
  identity.validate_cluster_id(cluster_id)
  identity.validate_node_id(self_node_id)
  iface = interface_name(cluster_id)
  out: list[list[str]] = []
  peers_sorted = sorted(
    (p for p in peer_table if int(p.get("node_id", 0)) != self_node_id),
    key=lambda p: (int(p.get("cluster_id", 0)), int(p.get("node_id", 0))),
  )
  for peer in peers_sorted:
    p_cluster = int(peer.get("cluster_id", 0))
    if p_cluster != cluster_id:
      raise ValueError(
        f"infra: peer cluster mismatch (self={cluster_id}, peer={p_cluster})"
      )
    p_node = int(peer.get("node_id", 0))
    p_under = identity.underlay_ipv4(p_cluster, p_node)
    out.append([
      "bridge", "fdb", "append", BROADCAST_MAC,
      "dev", iface,
      "dst", p_under,
    ])
  return out


def render_etc_hosts_block(
  cluster_id: int,
  peer_table: Iterable[Mapping[str, object]],
) -> str:
  """Pure: render the /etc/hosts block for `cluster_id`.

  Bracketed by `# BEGIN core-infra c<cluster>` / `# END core-infra
  c<cluster>` so re-rendering replaces the block in place. Sorted by
  node_id for deterministic output. Each line:
    `<inner_ipv4>\\t<hostname>`
  """
  identity.validate_cluster_id(cluster_id)
  begin = hosts_begin_marker(cluster_id)
  end = hosts_end_marker(cluster_id)
  entries = sorted(
    (p for p in peer_table if int(p.get("cluster_id", 0)) == cluster_id),
    key=lambda p: int(p.get("node_id", 0)),
  )
  lines: list[str] = [begin]
  for peer in entries:
    p_node = int(peer.get("node_id", 0))
    identity.validate_node_id(p_node)
    addr = identity.overlay_ipv4(cluster_id, p_node)
    host = identity.hostname(cluster_id, p_node)
    lines.append(f"{addr}\t{host}")
  lines.append(end)
  return "\n".join(lines) + "\n"


def apply_etc_hosts_block(
  current: str,
  cluster_id: int,
  block_str: str,
) -> str:
  """Pure: replace (or append) the BEGIN/END-bracketed block.

  Used both by tests and by the host-side script via stdin. Idempotent:
  re-applying the same block to an already-updated file yields the
  same file.
  """
  begin = hosts_begin_marker(cluster_id)
  end = hosts_end_marker(cluster_id)
  if not block_str.endswith("\n"):
    block_str = block_str + "\n"
  src_lines = current.splitlines(keepends=True)
  out: list[str] = []
  in_block = False
  replaced = False
  for line in src_lines:
    stripped = line.strip()
    if not in_block and stripped == begin:
      out.append(block_str)
      in_block = True
      replaced = True
      continue
    if in_block:
      if stripped == end:
        in_block = False
      continue
    out.append(line)
  if not replaced:
    if out and not out[-1].endswith("\n"):
      out.append("\n")
    out.append(block_str)
  return "".join(out)


_ETC_HOSTS_UPDATE_SCRIPT = (
  "import os, sys\n"
  "path = os.environ['INFRA_HOSTS_PATH']\n"
  "begin = os.environ['INFRA_HOSTS_BEGIN']\n"
  "end = os.environ['INFRA_HOSTS_END']\n"
  "block = sys.stdin.read()\n"
  "if not block.endswith('\\n'):\n"
  "    block = block + '\\n'\n"
  "src = open(path).read() if os.path.exists(path) else ''\n"
  "out = []\n"
  "in_block = False\n"
  "replaced = False\n"
  "for line in src.splitlines(keepends=True):\n"
  "    s = line.strip()\n"
  "    if not in_block and s == begin:\n"
  "        out.append(block)\n"
  "        in_block = True\n"
  "        replaced = True\n"
  "        continue\n"
  "    if in_block:\n"
  "        if s == end:\n"
  "            in_block = False\n"
  "        continue\n"
  "    out.append(line)\n"
  "if not replaced:\n"
  "    if out and not out[-1].endswith('\\n'):\n"
  "        out.append('\\n')\n"
  "    out.append(block)\n"
  "tmp = path + '.infra.tmp'\n"
  "with open(tmp, 'w') as f:\n"
  "    f.write(''.join(out))\n"
  "os.chmod(tmp, 0o644)\n"
  "os.replace(tmp, path)\n"
)


# --- SSH-apply functions ----------------------------------------------


def apply_vxlan(
  ssh_target: str,
  cluster_id: int,
  ip_link_argv: list[str],
  fdb_argv_list: list[list[str]],
  *,
  sudo: bool = True,
  runner: ssh.Runner | None = None,
) -> None:
  """SSH-apply the VXLAN device + FDB entries.

  Idempotent: if the iface already exists, delete then re-add. Then
  set it up and append broadcast-replication FDB entries.
  """
  runner = runner or ssh._default_runner
  iface = interface_name(cluster_id)
  q_iface = shlex.quote(iface)
  parts: list[str] = [
    "set -e",
    f"if ip link show {q_iface} >/dev/null 2>&1; then "
    f"ip link delete {q_iface}; fi",
    " ".join(shlex.quote(a) for a in ip_link_argv),
    f"ip link set {q_iface} up",
  ]
  for fdb in fdb_argv_list:
    parts.append(" ".join(shlex.quote(a) for a in fdb))
  cmd = "; ".join(parts)
  res = ssh.ssh_run(ssh_target, cmd, sudo=sudo, runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: vxlan apply failed on {ssh_target}: "
      f"{res.stderr.strip() or res.rc}"
    )


def update_etc_hosts(
  ssh_target: str,
  cluster_id: int,
  block_str: str,
  *,
  sudo: bool = True,
  runner: ssh.Runner | None = None,
) -> None:
  """SSH-apply the /etc/hosts block for `cluster_id` idempotently.

  Replaces only the BEGIN/END-bracketed region. If markers don't
  exist yet, the new block is appended. The replacement runs
  server-side via a python -c one-liner (python3 is a baseline
  Debian/Ubuntu install) so we keep round-trip count to one.
  """
  runner = runner or ssh._default_runner
  begin = hosts_begin_marker(cluster_id)
  end = hosts_end_marker(cluster_id)
  py = _ETC_HOSTS_UPDATE_SCRIPT
  # Pass path/markers/block via env to avoid quoting hell in argv.
  cmd = (
    f"INFRA_HOSTS_PATH={shlex.quote(ETC_HOSTS_PATH)} "
    f"INFRA_HOSTS_BEGIN={shlex.quote(begin)} "
    f"INFRA_HOSTS_END={shlex.quote(end)} "
    f"python3 -c {shlex.quote(py)}"
  )
  res = ssh.ssh_run(ssh_target, cmd, stdin=block_str, sudo=sudo, runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: /etc/hosts update failed on {ssh_target}: "
      f"{res.stderr.strip() or res.rc}"
    )


# --- systemd unit ExecStart line builders -----------------------------


def render_unit_execstart_lines(
  cluster_id: int,
  wg_dev_name: str,
  peer_table: Iterable[Mapping[str, object]],
  self_node_id: int,
  dstport: int = DEFAULT_DSTPORT,
  mtu: int = DEFAULT_INNER_MTU,
) -> list[str]:
  """Render the ExecStart= / ExecStartPre= / ExecStartPost= lines.

  Used by vxlan_cmd to substitute into the systemd template at install
  time. Idempotence on restart: ExecStartPre deletes the iface if
  present so a fresh ExecStart re-adds it.

  Returns the EXECSTART_BLOCK as a list of lines (no leading/trailing
  newline) ready to be joined with `\\n`.
  """
  iface = interface_name(cluster_id)
  ip_link = render_ip_link_args(cluster_id, wg_dev_name, dstport=dstport, mtu=mtu)
  fdbs = render_fdb_appends(cluster_id, peer_table, self_node_id)

  lines: list[str] = []
  lines.append(
    f"ExecStartPre=/bin/sh -c 'ip link show {iface} >/dev/null 2>&1 "
    f"&& ip link delete {iface} || true'"
  )
  lines.append("ExecStart=/sbin/ip " + " ".join(ip_link[1:]))
  lines.append(f"ExecStartPost=/sbin/ip link set {iface} up")
  for fdb in fdbs:
    lines.append("ExecStartPost=/sbin/" + " ".join(fdb))
  lines.append(f"ExecStop=/sbin/ip link delete {iface}")
  return lines
