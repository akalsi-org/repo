from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import decommission, inventory


class _Runner:
  def __init__(self, rc=0):
    self.rc = rc
    self.calls = []

  def __call__(self, argv, text=True, capture_output=True, check=False):
    self.calls.append(list(argv))
    return subprocess.CompletedProcess(argv, self.rc, "", "boom" if self.rc else "")


class DecommissionTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.root = pathlib.Path(self._tmp.name)
    (self.root / "bootstrap/providers").mkdir(parents=True)
    (self.root / "bootstrap/providers/hetzner.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    inventory.upsert(self.root, {
      "provider_label": "hetzner",
      "ssh_target": "root@198.51.100.10",
      "cluster_id": 7,
      "node_id": 3,
      "hetzner_vm_id": "12345",
    })

  def test_hetzner_destroy_removes_inventory(self):
    runner = _Runner()
    args = decommission.build_parser().parse_args(["hetzner", "12345"])
    rc = decommission.run(args, repo_root=self.root, runner=runner)
    self.assertEqual(rc, 0)
    self.assertEqual(runner.calls[0][1:], ["destroy_vm", "12345"])
    self.assertEqual(inventory.load(self.root)["hosts"], [])

  def test_provider_failure_raises_and_keeps_inventory(self):
    runner = _Runner(rc=1)
    args = decommission.build_parser().parse_args(["hetzner", "12345"])
    with self.assertRaises(SystemExit):
      decommission.run(args, repo_root=self.root, runner=runner)
    self.assertEqual(len(inventory.load(self.root)["hosts"]), 1)

  def test_contabo_returns_actionable_message(self):
    args = decommission.build_parser().parse_args(["contabo", "abc"])
    rc = decommission.run(args, repo_root=self.root, runner=_Runner())
    self.assertEqual(rc, 1)


if __name__ == "__main__":
  unittest.main()
