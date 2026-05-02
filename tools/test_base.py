from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock


class RepoTestCase(unittest.TestCase):
  def setUp(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self.root = pathlib.Path(self._tmp.name)

  def tearDown(self) -> None:
    self._tmp.cleanup()

  def write(self, rel: str, text: str) -> pathlib.Path:
    path = self.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

  def mock_subprocess_run(self):
    return mock.patch("subprocess.run")

  def assert_no_hardcoded_github_identity(self, text: str) -> None:
    self.assertNotIn("github.com/akalsi", text)
    self.assertNotIn("akalsi-org", text)
