"""WireGuard underlay helpers (ADR-0014, issue #4).

Pure functions where possible. SSH-touching functions accept a
runner so tests can mock the wire boundary.

Layout on the host (NEVER under repo root):
- /etc/wireguard/wg-c<cluster>.key   (mode 0600, owner root)
- /etc/wireguard/wg-c<cluster>.pub
- /etc/wireguard/wg-c<cluster>.conf  (mode 0600, owner root)
- /etc/systemd/system/wg-overlay@.service  (rendered from template)

The interface name is `wg-c<cluster>` so wg-quick can pick the
matching `.conf` automatically. The systemd unit is templated as
`wg-overlay@<cluster>.service` and uses %i in ExecStart.
"""
from __future__ import annotations

import shlex
from typing import Iterable, Mapping

from tools.infra_pkg import identity, ssh


WG_DIR = "/etc/wireguard"
DEFAULT_LISTEN_PORT = 51820
WG_PREFIX_LEN = 16  # /16 underlay per ADR-0014
WG_UNIT_TEMPLATE = "wg-overlay@.service.in"
WG_UNIT_INSTALL_PATH = "/etc/systemd/system/wg-overlay@.service"


def _int_field(value: object, *, default: int = 0) -> int:
  if value is None:
    return default
  if isinstance(value, int):
    return value
  if isinstance(value, str):
    return int(value)
  raise ValueError(f"infra: expected int-like field, got {type(value).__name__}")


def keypair_paths(cluster_id: int) -> tuple[str, str]:
  """Return (private_key_path, public_key_path) for `cluster_id`.

  Pure function; no I/O. Path layout matches `WG_DIR` constant.
  """
  identity.validate_cluster_id(cluster_id)
  base = f"{WG_DIR}/wg-c{cluster_id}"
  return (f"{base}.key", f"{base}.pub")


def conf_path(cluster_id: int) -> str:
  identity.validate_cluster_id(cluster_id)
  return f"{WG_DIR}/wg-c{cluster_id}.conf"


def interface_name(cluster_id: int) -> str:
  identity.validate_cluster_id(cluster_id)
  return f"wg-c{cluster_id}"


def generate_keypair(
  cluster_id: int,
  ssh_target: str,
  *,
  sudo: bool = True,
  runner: ssh.Runner | None = None,
) -> tuple[str, str]:
  """Generate a WG keypair on `ssh_target`. Idempotent.

  If the private key file already exists, just read its public key
  back via `wg pubkey`. Otherwise create with strict perms:

    umask 077; wg genkey | tee <priv> >/dev/null
    chmod 0600 <priv>; chown root:root <priv>
    wg pubkey < <priv> > <pub>; chmod 0644 <pub>; chown root:root <pub>

  Returns (private_key_path, public_key_string). The private key
  string is never returned and never crosses the SSH boundary back.
  """
  runner = runner or ssh._default_runner
  priv, pub = keypair_paths(cluster_id)
  q_priv = shlex.quote(priv)
  q_pub = shlex.quote(pub)
  q_dir = shlex.quote(WG_DIR)
  cmd = (
    "set -e; "
    f"install -d -m 0700 -o root -g root {q_dir}; "
    f"if [ ! -s {q_priv} ]; then "
    f"  umask 077; wg genkey | tee {q_priv} >/dev/null; "
    f"  chmod 0600 {q_priv}; chown root:root {q_priv}; "
    f"  wg pubkey < {q_priv} > {q_pub}; "
    f"  chmod 0644 {q_pub}; chown root:root {q_pub}; "
    "fi; "
    f"cat {q_pub}"
  )
  res = ssh.ssh_run(ssh_target, cmd, sudo=sudo, runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: wg keypair gen failed on {ssh_target}: "
      f"{res.stderr.strip() or res.rc}"
    )
  pub_str = res.stdout.strip()
  if not pub_str:
    raise SystemExit(f"infra: wg pubkey empty for {ssh_target}")
  return priv, pub_str


def render_wg_config(
  cluster_id: int,
  node_id: int,
  peer_table: Iterable[Mapping[str, object]],
  listen_port: int = DEFAULT_LISTEN_PORT,
  private_key_ref: str = "/etc/wireguard/wg-c{cluster}.key",
) -> str:
  """Pure function. Render `wg-c<cluster>.conf` from the peer table.

  Each entry in `peer_table` is a mapping with at least:
    - cluster_id (int) — must equal `cluster_id`
    - node_id (int)
    - wg_pubkey (str)
    - wg_underlay_endpoint (str, "host:port"); may be "" for self
  Self entry (own node_id) is skipped — only foreign peers go in.

  PrivateKey field uses a `PostUp` indirection so the actual key
  never appears in the rendered text: wg-quick reads the file at
  bring-up time, not from the conf.
  """
  identity.validate_cluster_id(cluster_id)
  identity.validate_node_id(node_id)
  if not isinstance(listen_port, int) or listen_port < 1 or listen_port > 65535:
    raise ValueError(f"infra: bad listen_port {listen_port!r}")

  self_addr = identity.underlay_ipv4(cluster_id, node_id)
  priv_path = private_key_ref.format(cluster=cluster_id)

  lines: list[str] = []
  lines.append("# managed by infra wg-up; do not edit by hand")
  lines.append(f"# cluster={cluster_id} node={node_id}")
  lines.append("[Interface]")
  lines.append(f"Address = {self_addr}/{WG_PREFIX_LEN}")
  lines.append(f"ListenPort = {listen_port}")
  # PostUp reads the on-disk key; wg-quick supports `PrivateKey =` but
  # we keep the file-only path so the .conf can stay 0600 without
  # holding a secret literal. This matches the ADR rule that secrets
  # never appear inside any rendered config we might log or diff.
  lines.append(f"PostUp = wg set %i private-key {priv_path}")

  peers_sorted = sorted(
    (p for p in peer_table if _int_field(p.get("node_id")) != node_id),
    key=lambda p: (_int_field(p.get("cluster_id")), _int_field(p.get("node_id"))),
  )
  for peer in peers_sorted:
    p_cluster = _int_field(peer.get("cluster_id"))
    if p_cluster != cluster_id:
      raise ValueError(
        f"infra: peer cluster mismatch (self={cluster_id}, peer={p_cluster})"
      )
    p_node = _int_field(peer.get("node_id"))
    p_pub = str(peer.get("wg_pubkey", "")).strip()
    if not p_pub:
      raise ValueError(f"infra: peer node {p_node} has empty wg_pubkey")
    p_endpoint = str(peer.get("wg_underlay_endpoint", "")).strip()
    p_addr = identity.underlay_ipv4(p_cluster, p_node)
    lines.append("")
    lines.append(f"# peer node={p_node}")
    lines.append("[Peer]")
    lines.append(f"PublicKey = {p_pub}")
    if p_endpoint:
      lines.append(f"Endpoint = {p_endpoint}")
    lines.append(f"AllowedIPs = {p_addr}/32")
    lines.append("PersistentKeepalive = 25")
  lines.append("")
  return "\n".join(lines)


def apply_wg_config(
  ssh_target: str,
  cluster_id: int,
  config_str: str,
  *,
  sudo: bool = True,
  runner: ssh.Runner | None = None,
) -> None:
  """Write `config_str` to /etc/wireguard/wg-c<cluster>.conf.

  Uses ssh + tee with umask 077 so the file lands at 0600. Final
  chmod + chown nail the ownership. The ssh.scp_write helper sets
  0644 by default, which is wrong for a wg config that may carry a
  pre-shared key in future slices, so we do the write inline here.
  """
  runner = runner or ssh._default_runner
  path = conf_path(cluster_id)
  q = shlex.quote(path)
  cmd = (
    "set -e; "
    f"install -d -m 0700 -o root -g root {shlex.quote(WG_DIR)}; "
    f"umask 077; cat > {q}; "
    f"chmod 0600 {q}; chown root:root {q}"
  )
  res = ssh.ssh_run(ssh_target, cmd, stdin=config_str, sudo=sudo, runner=runner)
  if res.rc != 0:
    raise SystemExit(
      f"infra: wg config write failed on {ssh_target}: "
      f"{res.stderr.strip() or res.rc}"
    )
