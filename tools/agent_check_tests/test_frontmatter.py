from __future__ import annotations

import unittest

from tools.agent_check import _frontmatter


class FrontmatterTest(unittest.TestCase):
  def test_well_formed(self) -> None:
    fm = _frontmatter("---\nname: x\ndescription: y\n---\nbody")
    self.assertEqual(fm, {"name": "x", "description": "y"})

  def test_missing(self) -> None:
    self.assertIsNone(_frontmatter("body"))

  def test_unterminated(self) -> None:
    self.assertIsNone(_frontmatter("---\nname: x\nbody"))

  def test_extra_fields_preserved(self) -> None:
    fm = _frontmatter("---\nname: x\ndescription: y\nfoo: bar\n---\n")
    self.assertEqual(fm["foo"], "bar")


if __name__ == "__main__":
  unittest.main()
