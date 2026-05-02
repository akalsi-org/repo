from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import inventory, ssh, units_render, wg, wg_cmd


# --- pure helpers --------------------------------------------------------


class KeypairPathsTest(unittest.TestCase):
  def test_paths_for_cluster_7(self):
    priv, pub = wg.keypair_paths(7)
    self.assertEqual(priv, "/etc/wireguard/wg-c7.key")
    self.assertEqual(pub, "/etc/wireguard/wg-c7.pub")

  def test_conf_path(self):
    self.assertEqual(wg.conf_path(7), "/etc/wireguard/wg-c7.conf")

  def test_interface_name(self):
    self.assertEqual(wg.interface_name(7), "wg-c7")

  def test_bad_cluster_raises(self):
    with self.assertRaises(ValueError):
      wg.keypair_paths(0)
    with self.assertRaises(ValueError):
      wg.keypair_paths(256)


class RenderWgConfigTest(unittest.TestCase):
  def _peer(self, cluster: int, node: int, pub: str, ep: str = "") -> dict:
    return {
      "cluster_id": cluster,
      "node_id": node,
      "wg_pubkey": pub,
      "wg_underlay_endpoint": ep,
    }

  def test_self_only_no_peers(self):
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=[])
    self.assertIn("[Interface]", out)
    self.assertIn("Address = 10.200.7.3/16", out)
    self.assertIn(f"ListenPort = {wg.DEFAULT_LISTEN_PORT}", out)
    self.assertIn("PostUp = wg set %i private-key /etc/wireguard/wg-c7.key", out)
    self.assertNotIn("[Peer]", out)

  def test_one_peer_block_well_formed(self):
    peers = [self._peer(7, 5, "AAAAPUBKEY=", "1.2.3.4:51820")]
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)
    self.assertIn("[Peer]", out)
    self.assertIn("PublicKey = AAAAPUBKEY=", out)
    self.assertIn("Endpoint = 1.2.3.4:51820", out)
    self.assertIn("AllowedIPs = 10.200.7.5/32", out)
    self.assertIn("PersistentKeepalive = 25", out)

  def test_self_entry_skipped(self):
    peers = [
      self._peer(7, 3, "SELFKEY="),  # self
      self._peer(7, 5, "OTHERKEY=", "1.2.3.4:51820"),
    ]
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)
    self.assertNotIn("SELFKEY=", out)
    self.assertIn("OTHERKEY=", out)
    # Exactly one [Peer] block.
    self.assertEqual(out.count("[Peer]"), 1)

  def test_peers_sorted_by_node_id(self):
    peers = [
      self._peer(7, 9, "K9=", "9.9.9.9:51820"),
      self._peer(7, 2, "K2=", "2.2.2.2:51820"),
      self._peer(7, 5, "K5=", "5.5.5.5:51820"),
    ]
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)
    pos2 = out.index("K2=")
    pos5 = out.index("K5=")
    pos9 = out.index("K9=")
    self.assertLess(pos2, pos5)
    self.assertLess(pos5, pos9)

  def test_peer_in_other_cluster_rejected(self):
    peers = [self._peer(8, 5, "WRONGKEY=", "1.2.3.4:51820")]
    with self.assertRaises(ValueError):
      wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)

  def test_empty_pubkey_rejected(self):
    peers = [self._peer(7, 5, "", "1.2.3.4:51820")]
    with self.assertRaises(ValueError):
      wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)

  def test_peer_without_endpoint_renders_no_endpoint_line(self):
    peers = [self._peer(7, 5, "K=", "")]
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=peers)
    self.assertIn("PublicKey = K=", out)
    self.assertNotIn("Endpoint = ", out)

  def test_listen_port_override(self):
    out = wg.render_wg_config(
      cluster_id=7, node_id=3, peer_table=[], listen_port=12345,
    )
    self.assertIn("ListenPort = 12345", out)

  def test_bad_listen_port_raises(self):
    with self.assertRaises(ValueError):
      wg.render_wg_config(cluster_id=7, node_id=3, peer_table=[], listen_port=0)

  def test_no_private_key_literal_in_output(self):
    """Rendered config must NEVER contain a key literal — only file ref."""
    out = wg.render_wg_config(cluster_id=7, node_id=3, peer_table=[])
    self.assertNotIn("PrivateKey = ", out)
    self.assertIn("/etc/wireguard/wg-c7.key", out)


# --- mocked SSH boundary -------------------------------------------------


class _RecordingRunner:
  """Mock ssh.Runner. Capture argv and replay scripted (rc, stdout, stderr)."""

  def __init__(self, scripted=None):
    self.calls: list[tuple[list[str], str | None]] = []
    self._scripted = list(scripted or [])

  def __call__(self, argv, stdin):
    self.calls.append((argv, stdin))
    if self._scripted:
      rc, out, err = self._scripted.pop(0)
    else:
      rc, out, err = (0, "", "")
    return ssh.SshResult(rc=rc, stdout=out, stderr=err)


def _last_remote_cmd(call: tuple[list[str], str | None]) -> str:
  argv, _ = call
  return argv[-1]


class GenerateKeypairTest(unittest.TestCase):
  def test_issues_wg_genkey_and_returns_pubkey(self):
    runner = _RecordingRunner(scripted=[(0, "PUBKEY-ABC=\n", "")])
    priv, pub = wg.generate_keypair(7, "root@host", sudo=False, runner=runner)
    self.assertEqual(priv, "/etc/wireguard/wg-c7.key")
    self.assertEqual(pub, "PUBKEY-ABC=")
    self.assertEqual(len(runner.calls), 1)
    cmd = _last_remote_cmd(runner.calls[0])
    # Right wg invocations.
    self.assertIn("wg genkey", cmd)
    self.assertIn("wg pubkey", cmd)
    # Strict permission ops.
    self.assertIn("umask 077", cmd)
    self.assertIn("chmod 0600 /etc/wireguard/wg-c7.key", cmd)
    self.assertIn("chown root:root /etc/wireguard/wg-c7.key", cmd)
    # Idempotency guard.
    self.assertIn("if [ ! -s /etc/wireguard/wg-c7.key ]", cmd)

  def test_failure_raises(self):
    runner = _RecordingRunner(scripted=[(1, "", "permission denied")])
    with self.assertRaises(SystemExit):
      wg.generate_keypair(7, "root@host", sudo=False, runner=runner)

  def test_empty_pubkey_raises(self):
    runner = _RecordingRunner(scripted=[(0, "   \n", "")])
    with self.assertRaises(SystemExit):
      wg.generate_keypair(7, "root@host", sudo=False, runner=runner)

  def test_sudo_wraps_command(self):
    runner = _RecordingRunner(scripted=[(0, "P=\n", "")])
    wg.generate_keypair(7, "user@host", sudo=True, runner=runner)
    cmd = _last_remote_cmd(runner.calls[0])
    self.assertIn("sudo -n bash -lc", cmd)


class ApplyWgConfigTest(unittest.TestCase):
  def test_writes_with_strict_perms(self):
    runner = _RecordingRunner(scripted=[(0, "", "")])
    wg.apply_wg_config(
      "root@host", 7, "[Interface]\n", sudo=False, runner=runner,
    )
    self.assertEqual(len(runner.calls), 1)
    argv, stdin = runner.calls[0]
    self.assertEqual(stdin, "[Interface]\n")
    cmd = argv[-1]
    self.assertIn("umask 077", cmd)
    self.assertIn("/etc/wireguard/wg-c7.conf", cmd)
    self.assertIn("chmod 0600 /etc/wireguard/wg-c7.conf", cmd)
    self.assertIn("chown root:root /etc/wireguard/wg-c7.conf", cmd)


# --- unit template -------------------------------------------------------


class WgUnitTemplateTest(unittest.TestCase):
  def test_render_substitutes_cluster_id(self):
    out = units_render.render_template(
      wg.WG_UNIT_TEMPLATE, {"CLUSTER_ID": "7"},
    )
    self.assertIn("cluster 7", out)
    self.assertNotIn("${CLUSTER_ID}", out)

  def test_template_has_wantedby_multi_user(self):
    """Reboot survival: WantedBy=multi-user.target is mandatory."""
    src = (
      pathlib.Path(units_render.UNITS_DIR) / wg.WG_UNIT_TEMPLATE
    ).read_text(encoding="utf-8")
    self.assertIn("WantedBy=multi-user.target", src)

  def test_template_uses_wg_quick(self):
    src = (
      pathlib.Path(units_render.UNITS_DIR) / wg.WG_UNIT_TEMPLATE
    ).read_text(encoding="utf-8")
    self.assertIn("wg-quick up wg-c%i", src)
    self.assertIn("wg-quick down wg-c%i", src)


# --- wg_cmd subcommand handlers (inventory plumbing) --------------------


class _Inv:
  """Tiny temp-dir inventory harness for wg_cmd tests."""

  def __init__(self, test_case: unittest.TestCase):
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    self.root = pathlib.Path(tmp.name)

  def upsert(self, **fields) -> dict:
    base = {
      "provider_label": "contabo",
      "arch": "x86_64",
      "smt_state": "smt_on",
      "login_for_keys_sync": "",
      "adopted_at": "2026-05-01T00:00:00Z",
    }
    base.update(fields)
    inventory.upsert(self.root, base)
    return base


class WgPeerAddTest(unittest.TestCase):
  def test_symmetric_peer_insertion(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="PUB_A=", wg_underlay_endpoint="1.1.1.1:51820",
      wg_listen_port=51820, peers=[],
    )
    inv.upsert(
      ssh_target="root@b", cluster_id=7, node_id=2,
      wg_pubkey="PUB_B=", wg_underlay_endpoint="2.2.2.2:51820",
      wg_listen_port=51820, peers=[],
    )
    runner = _RecordingRunner(scripted=[
      (0, "0", ""),  # probe id -u for a
      (0, "", ""),   # apply_wg_config for a
      (0, "", ""),   # systemctl restart for a
      (0, "0", ""),  # probe for b
      (0, "", ""),   # apply for b
      (0, "", ""),   # restart for b
    ])
    args = wg_cmd._wg_peer_add_parser().parse_args(["root@a", "root@b"])
    rc = wg_cmd.wg_peer_add_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)

    data = inventory.load(inv.root)
    by_node = {h["node_id"]: h for h in data["hosts"]}
    self.assertEqual(len(by_node[1]["peers"]), 1)
    self.assertEqual(by_node[1]["peers"][0]["wg_pubkey"], "PUB_B=")
    self.assertEqual(by_node[1]["peers"][0]["wg_underlay_endpoint"], "2.2.2.2:51820")
    self.assertEqual(len(by_node[2]["peers"]), 1)
    self.assertEqual(by_node[2]["peers"][0]["wg_pubkey"], "PUB_A=")

  def test_missing_pubkey_rejected(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="", wg_underlay_endpoint="", wg_listen_port=51820, peers=[],
    )
    inv.upsert(
      ssh_target="root@b", cluster_id=7, node_id=2,
      wg_pubkey="PUB_B=", wg_underlay_endpoint="2.2.2.2:51820",
      wg_listen_port=51820, peers=[],
    )
    args = wg_cmd._wg_peer_add_parser().parse_args(["root@a", "root@b"])
    with self.assertRaises(SystemExit):
      wg_cmd.wg_peer_add_run(args, repo_root=inv.root, runner=_RecordingRunner())

  def test_cross_cluster_rejected(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="A=", wg_underlay_endpoint="1.1.1.1:51820",
      wg_listen_port=51820, peers=[],
    )
    inv.upsert(
      ssh_target="root@b", cluster_id=8, node_id=2,
      wg_pubkey="B=", wg_underlay_endpoint="2.2.2.2:51820",
      wg_listen_port=51820, peers=[],
    )
    args = wg_cmd._wg_peer_add_parser().parse_args(["root@a", "root@b"])
    with self.assertRaises(SystemExit):
      wg_cmd.wg_peer_add_run(args, repo_root=inv.root, runner=_RecordingRunner())

  def test_dry_run_records_inventory_no_ssh(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="A=", wg_underlay_endpoint="1.1.1.1:51820",
      wg_listen_port=51820, peers=[],
    )
    inv.upsert(
      ssh_target="root@b", cluster_id=7, node_id=2,
      wg_pubkey="B=", wg_underlay_endpoint="2.2.2.2:51820",
      wg_listen_port=51820, peers=[],
    )
    runner = _RecordingRunner()
    args = wg_cmd._wg_peer_add_parser().parse_args(
      ["root@a", "root@b", "--dry-run"]
    )
    rc = wg_cmd.wg_peer_add_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    self.assertEqual(runner.calls, [])  # no SSH issued
    data = inventory.load(inv.root)
    by_node = {h["node_id"]: h for h in data["hosts"]}
    self.assertEqual(len(by_node[1]["peers"]), 1)
    self.assertEqual(len(by_node[2]["peers"]), 1)


class WgUpDryRunTest(unittest.TestCase):
  def test_default_endpoint_strips_user_at(self):
    self.assertEqual(
      wg_cmd._default_endpoint("root@198.51.100.7", 51820),
      "198.51.100.7:51820",
    )
    self.assertEqual(
      wg_cmd._default_endpoint("user@host.example.com", 12345),
      "host.example.com:12345",
    )

  def test_dry_run_skips_ssh(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@1.2.3.4", cluster_id=7, node_id=3,
      wg_pubkey="", wg_underlay_endpoint="", wg_listen_port=51820, peers=[],
    )
    runner = _RecordingRunner()
    args = wg_cmd._wg_up_parser().parse_args(["root@1.2.3.4", "--dry-run"])
    rc = wg_cmd.wg_up_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    self.assertEqual(runner.calls, [])


if __name__ == "__main__":
  unittest.main()
