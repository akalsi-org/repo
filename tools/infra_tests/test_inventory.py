from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import inventory


class InventoryRoundTripTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.root = pathlib.Path(self._tmp.name)

  def _host(self, cluster_id: int, node_id: int) -> dict:
    return {
      "provider_label": "contabo",
      "ssh_target": f"root@host-{node_id}",
      "cluster_id": cluster_id,
      "node_id": node_id,
      "arch": "x86_64",
      "smt_state": "smt_on",
      "login_for_keys_sync": "synth",
      "adopted_at": "2026-05-01T00:00:00Z",
    }

  def test_load_empty_returns_empty_list(self):
    data = inventory.load(self.root)
    self.assertEqual(data, {"hosts": []})

  def test_upsert_writes_file_and_round_trips(self):
    inventory.upsert(self.root, self._host(7, 3))
    p = inventory.inventory_path(self.root)
    self.assertTrue(p.is_file())
    raw = json.loads(p.read_text(encoding="utf-8"))
    self.assertEqual(len(raw["hosts"]), 1)
    self.assertEqual(raw["hosts"][0]["ssh_target"], "root@host-3")

  def test_upsert_replaces_existing_by_cluster_node(self):
    inventory.upsert(self.root, self._host(7, 3))
    new = self._host(7, 3)
    new["ssh_target"] = "root@host-3-renamed"
    inventory.upsert(self.root, new)
    data = inventory.load(self.root)
    self.assertEqual(len(data["hosts"]), 1)
    self.assertEqual(data["hosts"][0]["ssh_target"], "root@host-3-renamed")

  def test_upsert_orders_by_cluster_then_node(self):
    inventory.upsert(self.root, self._host(7, 5))
    inventory.upsert(self.root, self._host(7, 1))
    inventory.upsert(self.root, self._host(2, 9))
    data = inventory.load(self.root)
    keys = [(h["cluster_id"], h["node_id"]) for h in data["hosts"]]
    self.assertEqual(keys, [(2, 9), (7, 1), (7, 5)])

  def test_missing_required_field_raises(self):
    with self.assertRaises(SystemExit):
      inventory.upsert(self.root, {"ssh_target": "x"})


if __name__ == "__main__":
  unittest.main()
