from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import tuning


class TuningTest(unittest.TestCase):
  def test_required_sysctls_present(self):
    keys = {k for k, _ in tuning.SYSCTL_SETTINGS}
    self.assertIn("net.core.rmem_max", keys)
    self.assertIn("net.core.wmem_max", keys)
    self.assertIn("net.ipv4.udp_mem", keys)
    self.assertIn("net.core.netdev_max_backlog", keys)
    self.assertTrue(any(k.startswith("net.ipv4.tcp_") for k in keys))

  def test_dropin_path_under_sysctl_d(self):
    self.assertTrue(tuning.SYSCTL_DROPIN_PATH.startswith("/etc/sysctl.d/"))

  def test_render_dropin_round_trips_each_setting(self):
    body = tuning.render_sysctl_dropin()
    for key, value in tuning.SYSCTL_SETTINGS:
      self.assertIn(f"{key} = {value}", body)


if __name__ == "__main__":
  unittest.main()
