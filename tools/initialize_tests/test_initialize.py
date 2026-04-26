from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import sys
import tempfile
import unittest


def load_initialize_module():
  path = pathlib.Path(__file__).resolve().parents[1] / "initialize"
  loader = importlib.machinery.SourceFileLoader("initialize_cmd", str(path))
  spec = importlib.util.spec_from_loader(loader.name, loader)
  assert spec is not None
  module = importlib.util.module_from_spec(spec)
  sys.modules[loader.name] = module
  loader.exec_module(module)
  return module


initialize = load_initialize_module()


class InitializeTest(unittest.TestCase):
  def test_seeded_receipt_surfaces_one_ready_bet(self) -> None:
    with tempfile.TemporaryDirectory() as td:
      root = pathlib.Path(td)
      initialize.REPO_ROOT = root
      initialize.REPO_LOCAL = root / ".local"
      initialize.STAMP = initialize.REPO_LOCAL / "stamps" / "initialized"
      initialize.REPO_JSON = root / ".agents" / "repo.json"
      initialize.LICENSE_PATH = root / "LICENSE"
      initialize.README_PATH = root / "README.md"
      initialize.CONTEXT_PATH = root / "CONTEXT.md"
      initialize.TARGETS_PATH = root / ".agents" / "targets" / "targets.jsonl"
      initialize.IDEAS_PATH = root / ".agents" / "ideas" / "ideas.jsonl"
      initialize.ADR_DIR = root / "docs" / "adr"
      initialize.ADR_INDEX = initialize.ADR_DIR / "index.md"
      initialize.FIRST_ADR = initialize.ADR_DIR / "0001_template_adoption.md"

      initialize.seed_operating_pack({})

      receipt = initialize.next_bet_receipt()

    self.assertEqual(receipt[0], "  ready bet:     product-shape-operating-loop - Shape first product operating loop")
    self.assertEqual(receipt[1], "  proof:         target=product-operating-loop owner=ideas")
    self.assertEqual(receipt[2], "  run now:       ./repo.sh ideas ready")
    self.assertEqual(receipt[3], "  check:         ./repo.sh ideas ready")


if __name__ == "__main__":
  unittest.main()
