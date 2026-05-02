from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import inventory, provision_hetzner


class _Runner:
  def __init__(self):
    self.calls: list[tuple[list[str], str | None]] = []

  def __call__(self, argv, input=None, text=True, capture_output=True, check=False):
    self.calls.append((list(argv), input))
    if argv[1:] == ["region_list"]:
      return subprocess.CompletedProcess(argv, 0, "fsn1\nnbg1\n", "")
    if argv[1:] == ["size_list", "--arch=arm64"]:
      return subprocess.CompletedProcess(argv, 0, "cax11\ncax21\n", "")
    if argv[1:] == ["size_list", "--arch=amd64"]:
      return subprocess.CompletedProcess(argv, 0, "ccx13\ncx23\n", "")
    if len(argv) > 2 and argv[1] == "create_vm":
      return subprocess.CompletedProcess(argv, 0, "12345 198.51.100.10\n", "")
    if argv[0] == "ssh":
      return subprocess.CompletedProcess(argv, 0, "WG_PUBKEY=\n", "")
    return subprocess.CompletedProcess(argv, 1, "", f"unexpected {argv!r}")


def _fake_login(req, timeout=15):
  class Resp:
    def __enter__(self):
      return self
    def __exit__(self, *_):
      return False
    def read(self):
      return json.dumps({"login": "runtime-login"}).encode("utf-8")
  return Resp()


class ProvisionHetznerTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.root = pathlib.Path(self._tmp.name)
    (self.root / "bootstrap/providers").mkdir(parents=True)
    (self.root / "bootstrap/providers/hetzner.sh").write_text("#!/bin/sh\n", encoding="utf-8")

  def test_prompt_logic_defaults_to_arm64_cax_and_records_inventory(self):
    runner = _Runner()
    answers = iter(["", "", "", "7", "3", "you are seed", ""])
    args = provision_hetzner.build_parser().parse_args(["--no-ssh-wait"])
    buf = io.StringIO()
    with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), redirect_stdout(buf):
      rc = provision_hetzner.run(
        args,
        repo_root=self.root,
        input_fn=lambda _prompt: next(answers),
        runner=runner,
        url_opener=_fake_login,
        sleep_fn=lambda _n: None,
      )
    self.assertEqual(rc, 0)
    create = [call for call in runner.calls if len(call[0]) > 2 and call[0][1] == "create_vm"][0][0]
    self.assertEqual(create[2:6], ["node-3-c7", "cax11", "fsn1", "-"])
    data = inventory.load(self.root)
    self.assertEqual(len(data["hosts"]), 1)
    host = data["hosts"][0]
    self.assertEqual(host["provider_label"], "hetzner")
    self.assertEqual(host["hetzner_vm_id"], "12345")
    self.assertEqual(host["ssh_target"], "root@198.51.100.10")
    self.assertEqual(host["arch"], "aarch64")

  def test_amd64_prints_contabo_hint(self):
    runner = _Runner()
    answers = iter(["fsn1", "cx23", "7", "3", "you are seed", ""])
    args = provision_hetzner.build_parser().parse_args(["--arch=amd64", "--no-ssh-wait"])
    buf = io.StringIO()
    with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), redirect_stdout(buf):
      provision_hetzner.run(
        args,
        repo_root=self.root,
        input_fn=lambda _prompt: next(answers),
        runner=runner,
        url_opener=_fake_login,
        sleep_fn=lambda _n: None,
      )
    self.assertIn("consider Contabo via adopt for x86 (#3)", buf.getvalue())

  def test_cloud_init_uses_github_keys_and_generates_wg_key_on_host(self):
    cfg = {
      "cluster_id": 7,
      "node_id": 3,
      "seeds": ["root@seed"],
      "login_for_keys_sync": "runtime-login",
      "ssh_pubkey_body": "",
      "smt": "leave",
    }
    out = provision_hetzner.render_cloud_init(cfg)
    self.assertIn("https://github.com/runtime-login.keys", out)
    self.assertIn("/etc/infra/seeds", out)
    self.assertIn("root@seed", out)
    self.assertIn("wg genkey", out)
    self.assertIn("/etc/wireguard/wg-c7.key", out)
    self.assertNotIn("HETZNER_TOKEN", out)

  def test_cloud_init_local_key_disables_github_sync(self):
    cfg = {
      "cluster_id": 7,
      "node_id": 3,
      "seeds": [],
      "login_for_keys_sync": "",
      "ssh_pubkey_body": "ssh-ed25519 AAAA test\n",
      "smt": "disable",
    }
    out = provision_hetzner.render_cloud_init(cfg)
    self.assertIn("ssh-ed25519 AAAA test", out)
    self.assertNotIn("github.com/", out)
    self.assertIn("nosmt", out)

  def test_wait_for_ssh_pubkey_mocked(self):
    runner = _Runner()
    pub = provision_hetzner.wait_for_ssh_and_pubkey(
      "198.51.100.10", 7, runner=runner, attempts=1, sleep_fn=lambda _n: None,
    )
    self.assertEqual(pub, "WG_PUBKEY=")


if __name__ == "__main__":
  unittest.main()
