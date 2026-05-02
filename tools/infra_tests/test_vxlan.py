from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import inventory, ssh, units_render, vxlan, vxlan_cmd


# --- pure helpers --------------------------------------------------------


class InterfaceNameTest(unittest.TestCase):
  def test_iface_name_for_cluster_7(self):
    self.assertEqual(vxlan.interface_name(7), "vxlan-c7")

  def test_iface_name_for_cluster_1(self):
    self.assertEqual(vxlan.interface_name(1), "vxlan-c1")

  def test_iface_name_bad_cluster_raises(self):
    with self.assertRaises(ValueError):
      vxlan.interface_name(0)
    with self.assertRaises(ValueError):
      vxlan.interface_name(256)


class InnerIPv4Test(unittest.TestCase):
  def test_low_node(self):
    self.assertEqual(vxlan.inner_ipv4(7, 3), "10.7.0.3")

  def test_high_node_splits_bytes(self):
    # node 258 = 0x102 -> high=1 low=2
    self.assertEqual(vxlan.inner_ipv4(7, 258), "10.7.1.2")

  def test_max_node(self):
    self.assertEqual(vxlan.inner_ipv4(7, 65535), "10.7.255.255")

  def test_subnet(self):
    self.assertEqual(vxlan.inner_subnet(7), "10.7.0.0/16")
    self.assertEqual(vxlan.inner_subnet(1), "10.1.0.0/16")


class RenderIpLinkArgsTest(unittest.TestCase):
  def test_default_args(self):
    argv = vxlan.render_ip_link_args(7, "wg-c7")
    self.assertEqual(argv, [
      "ip", "link", "add", "vxlan-c7",
      "type", "vxlan",
      "id", "7",
      "dev", "wg-c7",
      "dstport", "4789",
      "nolearning",
      "mtu", "1370",
    ])

  def test_default_mtu_is_1370(self):
    argv = vxlan.render_ip_link_args(3, "wg-c3")
    self.assertIn("1370", argv)

  def test_mtu_override_honored(self):
    argv = vxlan.render_ip_link_args(7, "wg-c7", mtu=1300)
    # "mtu" then value
    idx = argv.index("mtu")
    self.assertEqual(argv[idx + 1], "1300")

  def test_dstport_override_honored(self):
    argv = vxlan.render_ip_link_args(7, "wg-c7", dstport=8472)
    idx = argv.index("dstport")
    self.assertEqual(argv[idx + 1], "8472")

  def test_id_matches_cluster(self):
    argv = vxlan.render_ip_link_args(42, "wg-c42")
    idx = argv.index("id")
    self.assertEqual(argv[idx + 1], "42")

  def test_dev_is_wg_iface(self):
    argv = vxlan.render_ip_link_args(7, "wg-c7")
    idx = argv.index("dev")
    self.assertEqual(argv[idx + 1], "wg-c7")

  def test_bad_mtu_rejected(self):
    with self.assertRaises(ValueError):
      vxlan.render_ip_link_args(7, "wg-c7", mtu=-1)
    with self.assertRaises(ValueError):
      vxlan.render_ip_link_args(7, "wg-c7", mtu=99999)

  def test_bad_dstport_rejected(self):
    with self.assertRaises(ValueError):
      vxlan.render_ip_link_args(7, "wg-c7", dstport=0)

  def test_empty_dev_rejected(self):
    with self.assertRaises(ValueError):
      vxlan.render_ip_link_args(7, "")


def _peer(cluster: int, node: int) -> dict:
  return {"cluster_id": cluster, "node_id": node}


class RenderFdbAppendsTest(unittest.TestCase):
  def test_no_peers_yields_empty(self):
    self.assertEqual(vxlan.render_fdb_appends(7, [], 1), [])

  def test_excludes_self(self):
    peers = [_peer(7, 1), _peer(7, 2), _peer(7, 3)]
    out = vxlan.render_fdb_appends(7, peers, self_node_id=2)
    self.assertEqual(len(out), 2)
    # self node 2 shouldn't appear in any dst
    for argv in out:
      idx = argv.index("dst")
      self.assertNotEqual(argv[idx + 1], "10.200.7.2")

  def test_argv_shape(self):
    peers = [_peer(7, 5)]
    out = vxlan.render_fdb_appends(7, peers, self_node_id=1)
    self.assertEqual(len(out), 1)
    self.assertEqual(out[0], [
      "bridge", "fdb", "append", "00:00:00:00:00:00",
      "dev", "vxlan-c7",
      "dst", "10.200.7.5",
    ])

  def test_broadcast_mac_used(self):
    peers = [_peer(7, 5), _peer(7, 9)]
    out = vxlan.render_fdb_appends(7, peers, self_node_id=1)
    for argv in out:
      self.assertIn("00:00:00:00:00:00", argv)

  def test_peer_in_other_cluster_rejected(self):
    with self.assertRaises(ValueError):
      vxlan.render_fdb_appends(7, [_peer(8, 5)], self_node_id=1)

  def test_sorted_by_node_id(self):
    peers = [_peer(7, 9), _peer(7, 2), _peer(7, 5)]
    out = vxlan.render_fdb_appends(7, peers, self_node_id=1)
    dsts = [a[a.index("dst") + 1] for a in out]
    self.assertEqual(dsts, ["10.200.7.2", "10.200.7.5", "10.200.7.9"])


class RenderEtcHostsBlockTest(unittest.TestCase):
  def test_bracketed_with_begin_end_markers(self):
    out = vxlan.render_etc_hosts_block(7, [_peer(7, 1), _peer(7, 2)])
    self.assertIn("# BEGIN core-infra c7", out)
    self.assertIn("# END core-infra c7", out)

  def test_lines_for_each_peer(self):
    out = vxlan.render_etc_hosts_block(7, [_peer(7, 1), _peer(7, 2)])
    self.assertIn("10.7.0.1\tnode-1.c7", out)
    self.assertIn("10.7.0.2\tnode-2.c7", out)

  def test_deterministic_order(self):
    a = vxlan.render_etc_hosts_block(7, [_peer(7, 9), _peer(7, 2), _peer(7, 5)])
    b = vxlan.render_etc_hosts_block(7, [_peer(7, 5), _peer(7, 2), _peer(7, 9)])
    self.assertEqual(a, b)
    pos2 = a.index("node-2.c7")
    pos5 = a.index("node-5.c7")
    pos9 = a.index("node-9.c7")
    self.assertLess(pos2, pos5)
    self.assertLess(pos5, pos9)

  def test_filters_other_clusters(self):
    out = vxlan.render_etc_hosts_block(
      7, [_peer(7, 1), _peer(8, 2), _peer(7, 3)],
    )
    self.assertIn("node-1.c7", out)
    self.assertIn("node-3.c7", out)
    self.assertNotIn("node-2.c8", out)

  def test_high_node_id_ipv4_split(self):
    out = vxlan.render_etc_hosts_block(7, [_peer(7, 258)])
    self.assertIn("10.7.1.2\tnode-258.c7", out)


class ApplyEtcHostsBlockTest(unittest.TestCase):
  def test_appends_when_no_existing_block(self):
    block = vxlan.render_etc_hosts_block(7, [_peer(7, 1)])
    cur = "127.0.0.1 localhost\n"
    out = vxlan.apply_etc_hosts_block(cur, 7, block)
    self.assertTrue(out.startswith("127.0.0.1 localhost\n"))
    self.assertIn("# BEGIN core-infra c7", out)
    self.assertIn("# END core-infra c7", out)

  def test_idempotent_repeated_apply(self):
    block = vxlan.render_etc_hosts_block(7, [_peer(7, 1), _peer(7, 2)])
    cur = "127.0.0.1 localhost\n"
    once = vxlan.apply_etc_hosts_block(cur, 7, block)
    twice = vxlan.apply_etc_hosts_block(once, 7, block)
    self.assertEqual(once, twice)

  def test_replaces_existing_block(self):
    old_block = vxlan.render_etc_hosts_block(7, [_peer(7, 1)])
    new_block = vxlan.render_etc_hosts_block(7, [_peer(7, 1), _peer(7, 2)])
    cur = "127.0.0.1 localhost\n" + old_block + "tail line\n"
    out = vxlan.apply_etc_hosts_block(cur, 7, new_block)
    self.assertIn("node-2.c7", out)
    # tail content preserved
    self.assertIn("tail line", out)
    # exactly one BEGIN marker
    self.assertEqual(out.count("# BEGIN core-infra c7"), 1)
    self.assertEqual(out.count("# END core-infra c7"), 1)

  def test_other_cluster_block_untouched(self):
    block_c7 = vxlan.render_etc_hosts_block(7, [_peer(7, 1)])
    block_c8 = vxlan.render_etc_hosts_block(8, [_peer(8, 1)])
    cur = "127.0.0.1 localhost\n" + block_c8
    out = vxlan.apply_etc_hosts_block(cur, 7, block_c7)
    self.assertIn("# BEGIN core-infra c7", out)
    self.assertIn("# BEGIN core-infra c8", out)
    self.assertIn("node-1.c7", out)
    self.assertIn("node-1.c8", out)


# --- mocked SSH boundary -------------------------------------------------


class _RecordingRunner:
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


class ApplyVxlanTest(unittest.TestCase):
  def test_issues_delete_then_add_then_up_then_fdb(self):
    runner = _RecordingRunner(scripted=[(0, "", "")])
    ip_link = vxlan.render_ip_link_args(7, "wg-c7")
    fdbs = vxlan.render_fdb_appends(7, [_peer(7, 5)], self_node_id=1)
    vxlan.apply_vxlan(
      "root@host", 7, ip_link, fdbs, sudo=False, runner=runner,
    )
    cmd = _last_remote_cmd(runner.calls[0])
    self.assertIn("ip link show vxlan-c7", cmd)
    self.assertIn("ip link delete vxlan-c7", cmd)
    self.assertIn("ip link add vxlan-c7", cmd)
    self.assertIn("ip link set vxlan-c7 up", cmd)
    self.assertIn("bridge fdb append 00:00:00:00:00:00", cmd)
    self.assertIn("dst 10.200.7.5", cmd)

  def test_failure_raises(self):
    runner = _RecordingRunner(scripted=[(1, "", "boom")])
    with self.assertRaises(SystemExit):
      vxlan.apply_vxlan(
        "root@host", 7,
        vxlan.render_ip_link_args(7, "wg-c7"),
        [], sudo=False, runner=runner,
      )

  def test_sudo_wraps_command(self):
    runner = _RecordingRunner(scripted=[(0, "", "")])
    vxlan.apply_vxlan(
      "user@host", 7,
      vxlan.render_ip_link_args(7, "wg-c7"),
      [], sudo=True, runner=runner,
    )
    cmd = _last_remote_cmd(runner.calls[0])
    self.assertIn("sudo -n bash -lc", cmd)


class UpdateEtcHostsTest(unittest.TestCase):
  def test_passes_block_via_stdin(self):
    runner = _RecordingRunner(scripted=[(0, "", "")])
    block = vxlan.render_etc_hosts_block(7, [_peer(7, 1)])
    vxlan.update_etc_hosts(
      "root@host", 7, block, sudo=False, runner=runner,
    )
    self.assertEqual(len(runner.calls), 1)
    argv, stdin = runner.calls[0]
    self.assertEqual(stdin, block)
    cmd = argv[-1]
    self.assertIn("INFRA_HOSTS_PATH=/etc/hosts", cmd)
    self.assertIn("INFRA_HOSTS_BEGIN=", cmd)
    self.assertIn("INFRA_HOSTS_END=", cmd)
    self.assertIn("python3 -c", cmd)

  def test_failure_raises(self):
    runner = _RecordingRunner(scripted=[(2, "", "boom")])
    block = vxlan.render_etc_hosts_block(7, [_peer(7, 1)])
    with self.assertRaises(SystemExit):
      vxlan.update_etc_hosts(
        "root@host", 7, block, sudo=False, runner=runner,
      )


# --- unit template -------------------------------------------------------


class VxlanUnitTemplateTest(unittest.TestCase):
  def test_render_substitutes_cluster_id_and_block(self):
    out = units_render.render_template(
      vxlan.VXLAN_UNIT_TEMPLATE,
      {
        "CLUSTER_ID": "7",
        "EXECSTART_BLOCK": "ExecStart=/sbin/ip link add vxlan-c7 ...",
      },
    )
    self.assertIn("cluster 7", out)
    self.assertIn("ExecStart=/sbin/ip link add vxlan-c7 ...", out)
    self.assertNotIn("${CLUSTER_ID}", out)
    self.assertNotIn("${EXECSTART_BLOCK}", out)

  def test_template_has_wantedby_multi_user(self):
    src = (
      pathlib.Path(units_render.UNITS_DIR) / vxlan.VXLAN_UNIT_TEMPLATE
    ).read_text(encoding="utf-8")
    self.assertIn("WantedBy=multi-user.target", src)

  def test_template_after_and_requires_wg(self):
    src = (
      pathlib.Path(units_render.UNITS_DIR) / vxlan.VXLAN_UNIT_TEMPLATE
    ).read_text(encoding="utf-8")
    self.assertIn("After=", src)
    self.assertIn("wg-overlay@%i.service", src)
    self.assertIn("Requires=wg-overlay@%i.service", src)

  def test_template_oneshot_remain_after_exit(self):
    src = (
      pathlib.Path(units_render.UNITS_DIR) / vxlan.VXLAN_UNIT_TEMPLATE
    ).read_text(encoding="utf-8")
    self.assertIn("Type=oneshot", src)
    self.assertIn("RemainAfterExit=yes", src)


# --- vxlan_cmd inventory plumbing ----------------------------------------


class _Inv:
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


class VxlanUpDryRunTest(unittest.TestCase):
  def test_dry_run_skips_ssh(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@1.2.3.4", cluster_id=7, node_id=3,
      wg_pubkey="PUB=", wg_underlay_endpoint="1.2.3.4:51820",
      wg_listen_port=51820,
      peers=[{"cluster_id": 7, "node_id": 5,
              "wg_pubkey": "P5=", "wg_underlay_endpoint": "5.5.5.5:51820"}],
    )
    runner = _RecordingRunner()
    args = vxlan_cmd._vxlan_up_parser().parse_args(
      ["root@1.2.3.4", "--dry-run"]
    )
    rc = vxlan_cmd.vxlan_up_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    self.assertEqual(runner.calls, [])

  def test_missing_wg_pubkey_rejected(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@1.2.3.4", cluster_id=7, node_id=3,
      wg_pubkey="", wg_underlay_endpoint="", wg_listen_port=51820, peers=[],
    )
    args = vxlan_cmd._vxlan_up_parser().parse_args(["root@1.2.3.4"])
    with self.assertRaises(SystemExit):
      vxlan_cmd.vxlan_up_run(
        args, repo_root=inv.root, runner=_RecordingRunner(),
      )

  def test_unknown_target_rejected(self):
    inv = _Inv(self)
    args = vxlan_cmd._vxlan_up_parser().parse_args(["root@nope"])
    with self.assertRaises(SystemExit):
      vxlan_cmd.vxlan_up_run(
        args, repo_root=inv.root, runner=_RecordingRunner(),
      )


class VxlanUpFullFlowTest(unittest.TestCase):
  def test_runs_expected_ssh_sequence(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@1.2.3.4", cluster_id=7, node_id=3,
      wg_pubkey="PUB=", wg_underlay_endpoint="1.2.3.4:51820",
      wg_listen_port=51820,
      peers=[{"cluster_id": 7, "node_id": 5,
              "wg_pubkey": "P5=", "wg_underlay_endpoint": "5.5.5.5:51820"}],
    )
    runner = _RecordingRunner(scripted=[
      (0, "0", ""),  # probe id -u
      (0, "", ""),   # apply_vxlan
      (0, "", ""),   # update_etc_hosts (scp+chmod via ssh.scp_write? actually our update_etc_hosts uses ssh_run directly)
      (0, "", ""),   # scp_write unit
      (0, "", ""),   # systemctl daemon-reload
      (0, "", ""),   # systemctl enable+restart
    ])
    args = vxlan_cmd._vxlan_up_parser().parse_args(["root@1.2.3.4"])
    rc = vxlan_cmd.vxlan_up_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    # 6 SSH-ish round-trips expected.
    self.assertEqual(len(runner.calls), 6)
    # Inventory persists vxlan defaults.
    data = inventory.load(inv.root)
    h = next(h for h in data["hosts"] if h["ssh_target"] == "root@1.2.3.4")
    self.assertEqual(h["inner_mtu"], vxlan.DEFAULT_INNER_MTU)
    self.assertEqual(h["vxlan_dstport"], vxlan.DEFAULT_DSTPORT)

  def test_mtu_override_propagates(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@1.2.3.4", cluster_id=7, node_id=3,
      wg_pubkey="PUB=", wg_underlay_endpoint="1.2.3.4:51820",
      wg_listen_port=51820, peers=[],
    )
    runner = _RecordingRunner(scripted=[
      (0, "0", ""), (0, "", ""), (0, "", ""),
      (0, "", ""), (0, "", ""), (0, "", ""),
    ])
    args = vxlan_cmd._vxlan_up_parser().parse_args(
      ["root@1.2.3.4", "--mtu", "1280"]
    )
    rc = vxlan_cmd.vxlan_up_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    data = inventory.load(inv.root)
    h = next(h for h in data["hosts"] if h["ssh_target"] == "root@1.2.3.4")
    self.assertEqual(h["inner_mtu"], 1280)
    # The first apply_vxlan call carries `mtu 1280` in its argv.
    apply_cmd = _last_remote_cmd(runner.calls[1])
    self.assertIn("mtu 1280", apply_cmd)


class HostsRenderTest(unittest.TestCase):
  def test_dry_run_prints_block_no_ssh(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="A=", wg_underlay_endpoint="1.1.1.1:51820",
      wg_listen_port=51820,
      peers=[{"cluster_id": 7, "node_id": 2,
              "wg_pubkey": "B=", "wg_underlay_endpoint": "2.2.2.2:51820"}],
    )
    runner = _RecordingRunner()
    args = vxlan_cmd._hosts_render_parser().parse_args(["root@a", "--dry-run"])
    rc = vxlan_cmd.hosts_render_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    self.assertEqual(runner.calls, [])

  def test_apply_includes_self_and_peers(self):
    inv = _Inv(self)
    inv.upsert(
      ssh_target="root@a", cluster_id=7, node_id=1,
      wg_pubkey="A=", wg_underlay_endpoint="1.1.1.1:51820",
      wg_listen_port=51820,
      peers=[{"cluster_id": 7, "node_id": 2,
              "wg_pubkey": "B=", "wg_underlay_endpoint": "2.2.2.2:51820"}],
    )
    runner = _RecordingRunner(scripted=[(0, "0", ""), (0, "", "")])
    args = vxlan_cmd._hosts_render_parser().parse_args(["root@a"])
    rc = vxlan_cmd.hosts_render_run(args, repo_root=inv.root, runner=runner)
    self.assertEqual(rc, 0)
    # Last call carries the block as stdin.
    _, stdin = runner.calls[-1]
    self.assertIn("node-1.c7", stdin)
    self.assertIn("node-2.c7", stdin)


# --- dispatch wiring -----------------------------------------------------


class DispatchTest(unittest.TestCase):
  def test_subcommands_registered(self):
    from tools.infra_pkg import dispatch
    self.assertIn("vxlan-up", dispatch.SUBCOMMANDS)
    self.assertIn("hosts-render", dispatch.SUBCOMMANDS)


if __name__ == "__main__":
  unittest.main()
