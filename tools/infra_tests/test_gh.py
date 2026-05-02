from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.infra_pkg import gh


class _FakeResp:
  def __init__(self, body: bytes):
    self._body = body

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return False

  def read(self):
    return self._body


def _fake_opener_for(login: str):
  payload = json.dumps({"login": login, "id": 1}).encode("utf-8")
  def opener(req, timeout=15):
    # Confirm Authorization header is set so token gets used.
    auth = dict(req.header_items()).get("Authorization", "")
    if not auth.startswith("Bearer "):
      raise AssertionError(f"missing bearer auth, got {auth!r}")
    return _FakeResp(payload)
  return opener


class DiscoverLoginTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.home = pathlib.Path(self._tmp.name)
    (self.home / "github.token").write_text("fake-token-xyz", encoding="utf-8")
    self._orig_env = os.environ.pop("GITHUB_TOKEN", None)
    self.addCleanup(self._restore_env)

  def _restore_env(self):
    os.environ.pop("GITHUB_TOKEN", None)
    if self._orig_env is not None:
      os.environ["GITHUB_TOKEN"] = self._orig_env

  def test_default_path_calls_user_endpoint_and_returns_login(self):
    opener = _fake_opener_for("synth-discovered-login")
    out = gh.discover_login(home=self.home, opener=opener)
    self.assertEqual(out, "synth-discovered-login")

  def test_override_short_circuits_api(self):
    sentinel = mock.Mock(side_effect=AssertionError("opener should not be called"))
    out = gh.discover_login(override="other-login", home=self.home, opener=sentinel)
    self.assertEqual(out, "other-login")
    sentinel.assert_not_called()

  def test_override_empty_raises(self):
    with self.assertRaises(gh.GhDiscoveryError):
      gh.discover_login(override="   ", home=self.home, opener=lambda *a, **k: None)

  def test_env_token_wins(self):
    os.environ["GITHUB_TOKEN"] = "env-token"
    captured = {}
    def opener(req, timeout=15):
      captured["auth"] = dict(req.header_items()).get("Authorization", "")
      return _FakeResp(json.dumps({"login": "from-env"}).encode("utf-8"))
    out = gh.discover_login(home=self.home, opener=opener)
    self.assertEqual(out, "from-env")
    self.assertEqual(captured["auth"], "Bearer env-token")

  def test_missing_token_raises(self):
    (self.home / "github.token").unlink()
    with self.assertRaises(gh.GhDiscoveryError):
      gh.discover_login(home=self.home, opener=lambda *a, **k: None)

  def test_keys_url_format(self):
    self.assertEqual(
      gh.keys_url("synth-login"),
      "https://github.com/synth-login.keys",
    )


if __name__ == "__main__":
  unittest.main()
