from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


def load_system_test_module():
  path = pathlib.Path(__file__).resolve().parents[1] / "system_test"
  loader = importlib.machinery.SourceFileLoader("system_test_cmd", str(path))
  spec = importlib.util.spec_from_loader(loader.name, loader)
  assert spec is not None
  module = importlib.util.module_from_spec(spec)
  sys.modules[loader.name] = module
  loader.exec_module(module)
  return module


system_test = load_system_test_module()


class ManifestTest(unittest.TestCase):
  def write_manifest(self, data: object) -> pathlib.Path:
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    with tmp:
      json.dump(data, tmp)
    path = pathlib.Path(tmp.name)
    self.addCleanup(path.unlink)
    return path

  def test_default_shape_declares_cluster_and_backend_checks(self) -> None:
    path = self.write_manifest({
      "cluster_size": 3,
      "service_port": 8080,
      "host_port_base": 41000,
      "scenarios": {
        "plain": ["root", "toolchain", "cluster_ports"],
        "bwrap": ["bwrap_hosts"],
      },
    })

    manifest = system_test.load_manifest(path)

    self.assertEqual(manifest.cluster_size, 3)
    self.assertEqual(manifest.service_port, 8080)
    self.assertEqual(manifest.host_port_base, 41000)
    self.assertEqual(manifest.scenarios["plain"], ["root", "toolchain", "cluster_ports"])
    self.assertEqual(manifest.scenarios["bwrap"], ["bwrap_hosts"])

  def test_manifest_rejects_unknown_check(self) -> None:
    path = self.write_manifest({
      "cluster_size": 3,
      "service_port": 8080,
      "host_port_base": 41000,
      "scenarios": {
        "plain": ["cluster_ports"],
        "bwrap": ["root"],
      },
    })

    with self.assertRaisesRegex(ValueError, "unknown bwrap check `root`"):
      system_test.load_manifest(path)

  def test_manifest_rejects_missing_cluster_size(self) -> None:
    path = self.write_manifest({
      "scenarios": {
        "plain": ["root"],
      },
    })

    with self.assertRaisesRegex(ValueError, "cluster_size must be integer >= 1"):
      system_test.load_manifest(path)

  def test_explicit_backend_must_be_declared(self) -> None:
    path = self.write_manifest({
      "cluster_size": 3,
      "service_port": 8080,
      "host_port_base": 41000,
      "scenarios": {
        "plain": ["root"],
      },
    })
    manifest = system_test.load_manifest(path)

    with self.assertRaisesRegex(ValueError, "backend `bwrap` not declared"):
      system_test.backend_classes("bwrap", manifest)

  def test_cluster_nodes_share_service_port_with_distinct_host_ports(self) -> None:
    with tempfile.TemporaryDirectory() as td:
      nodes = system_test.cluster_nodes(pathlib.Path(td), 3, 8080, 41000)

    self.assertEqual([node.name for node in nodes], ["node-0", "node-1", "node-2"])
    self.assertEqual([node.ip for node in nodes], ["127.0.0.2", "127.0.0.3", "127.0.0.4"])
    self.assertEqual([node.service_port for node in nodes], [8080, 8080, 8080])
    self.assertEqual([node.host_port for node in nodes], [41000, 41001, 41002])

  def test_manifest_rejects_host_port_range_overflow(self) -> None:
    path = self.write_manifest({
      "cluster_size": 3,
      "service_port": 8080,
      "host_port_base": 65534,
      "scenarios": {
        "plain": ["root"],
      },
    })

    with self.assertRaisesRegex(ValueError, "host_port_base range exceeds 65535"):
      system_test.load_manifest(path)

  def test_cluster_mapping_lock_asserts_name_to_ip(self) -> None:
    with tempfile.TemporaryDirectory() as td:
      root = pathlib.Path(td)
      nodes = system_test.cluster_nodes(root / "cluster", 2, 8080, 41000)
      results = system_test.assert_cluster_mapping(root / "locks", nodes)

    self.assertEqual([result.status for result in results], ["PASS", "PASS"])

  def test_cluster_mapping_lock_rejects_duplicate_ip(self) -> None:
    with tempfile.TemporaryDirectory() as td:
      root = pathlib.Path(td)
      nodes = system_test.cluster_nodes(root / "cluster", 2, 8080, 41000)
      nodes[1].ip = nodes[0].ip
      results = system_test.assert_cluster_mapping(root / "locks", nodes)

    self.assertEqual([result.status for result in results], ["PASS", "FAIL"])

  def test_cluster_lock_dir_is_under_repo_local(self) -> None:
    self.assertTrue(system_test.cluster_lock_dir().is_relative_to(system_test.LOCAL))
    self.assertIn("system_test", system_test.cluster_lock_dir().parts)


if __name__ == "__main__":
  unittest.main()
