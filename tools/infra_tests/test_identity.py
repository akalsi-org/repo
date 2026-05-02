from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import identity


class IdentityTest(unittest.TestCase):
  def test_overlay_low_node(self):
    self.assertEqual(identity.overlay_ipv4(7, 1), "10.7.0.1")

  def test_overlay_high_node(self):
    # 65535 -> high=255, low=255
    self.assertEqual(identity.overlay_ipv4(7, 65535), "10.7.255.255")

  def test_overlay_split_node(self):
    # 300 -> 0x012C -> high=1 low=44
    self.assertEqual(identity.overlay_ipv4(7, 300), "10.7.1.44")

  def test_underlay_uses_node_low_only(self):
    self.assertEqual(identity.underlay_ipv4(7, 300), "10.200.7.44")

  def test_hostname_format(self):
    self.assertEqual(identity.hostname(7, 42), "node-42.c7")

  def test_validate_cluster_low(self):
    with self.assertRaises(ValueError):
      identity.validate_cluster_id(0)

  def test_validate_cluster_high(self):
    with self.assertRaises(ValueError):
      identity.validate_cluster_id(256)

  def test_validate_node_low(self):
    with self.assertRaises(ValueError):
      identity.validate_node_id(0)

  def test_validate_node_high(self):
    with self.assertRaises(ValueError):
      identity.validate_node_id(70000)


class EtcHostsTest(unittest.TestCase):
  def test_render_sorts_and_includes_both_addrs(self):
    peers = [
      identity.node_addrs(7, 3),
      identity.node_addrs(7, 1),
      identity.node_addrs(7, 2),
    ]
    out = identity.render_etc_hosts(peers)
    lines = [line for line in out.splitlines() if line and not line.startswith("#")]
    # 3 peers x 2 lines (overlay + underlay) = 6 entries
    self.assertEqual(len(lines), 6)
    # First peer (node 1) entries come before node 3 entries.
    self.assertTrue(lines[0].startswith("10.7.0.1\t"))
    self.assertTrue(lines[1].startswith("10.200.7.1\t"))
    self.assertIn("node-1.c7", lines[0])
    self.assertIn("node-1.c7-wg", lines[1])
    self.assertIn("node-3.c7", lines[4])


if __name__ == "__main__":
  unittest.main()
