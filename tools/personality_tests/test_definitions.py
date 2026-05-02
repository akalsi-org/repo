from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from tools.personality_pkg import definitions  # noqa: E402
from tools.personality_tests._fixtures import make_repo, write_personality  # noqa: E402


class YamlParserTest(unittest.TestCase):
  def test_parses_defaults_shape(self):
    text = (
      "schema_version: 1\n"
      "defaults:\n"
      "  claude:\n"
      "    command: claude\n"
      "    model: claude-sonnet-4-6\n"
      "    effort: null\n"
      "  codex:\n"
      "    command: codex\n"
      "    model: gpt-5.5\n"
      "    effort: low\n"
      "  copilot:\n"
      "    command: copilot\n"
      "    model: gpt-5.4\n"
      "    effort: null\n"
    )
    out = definitions.parse_yaml_minimal(text)
    self.assertEqual(out["schema_version"], 1)
    self.assertEqual(out["defaults"]["claude"]["model"], "claude-sonnet-4-6")
    self.assertIsNone(out["defaults"]["claude"]["effort"])
    self.assertEqual(out["defaults"]["codex"]["effort"], "low")

  def test_rejects_tabs(self):
    with self.assertRaises(definitions.DefinitionError):
      definitions.parse_yaml_minimal("a:\n\tb: 1\n")

  def test_strips_comments(self):
    out = definitions.parse_yaml_minimal("a: 1 # trailing comment\n# whole-line\nb: hi\n")
    self.assertEqual(out, {"a": 1, "b": "hi"})

  def test_lists_of_scalars(self):
    out = definitions.parse_yaml_minimal("delegates_to:\n  - cfo\n  - cto\n")
    self.assertEqual(out["delegates_to"], ["cfo", "cto"])

  def test_quoted_strings_preserve_inner_chars(self):
    out = definitions.parse_yaml_minimal('shell_allowlist:\n  - "./repo.sh personality ask *"\n')
    self.assertEqual(out["shell_allowlist"], ["./repo.sh personality ask *"])


class PersonalityFrontMatterTest(unittest.TestCase):
  def test_loads_minimal_personality(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      p = definitions.load_personality(root, "ceo")
      self.assertEqual(p.name, "ceo")
      self.assertEqual(p.cli, "claude")
      self.assertEqual(p.delegates_to, ())

  def test_rejects_unknown_field(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      pdir = root / ".agents/personalities/bad"
      pdir.mkdir(parents=True)
      (pdir / "personality.md").write_text(
        "---\nname: bad\ntitle: Bad\ncli: claude\nbogus: 1\n---\n\nbody\n",
        encoding="utf-8",
      )
      with self.assertRaises(definitions.DefinitionError):
        definitions.load_personality(root, "bad")

  def test_rejects_unknown_cli(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      pdir = root / ".agents/personalities/bad"
      pdir.mkdir(parents=True)
      (pdir / "personality.md").write_text(
        "---\nname: bad\ntitle: Bad\ncli: gemini\n---\n\nbody\n",
        encoding="utf-8",
      )
      with self.assertRaises(definitions.DefinitionError):
        definitions.load_personality(root, "bad")

  def test_rejects_name_mismatch(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      pdir = root / ".agents/personalities/foo"
      pdir.mkdir(parents=True)
      (pdir / "personality.md").write_text(
        "---\nname: bar\ntitle: Bar\ncli: claude\n---\n\nbody\n",
        encoding="utf-8",
      )
      with self.assertRaises(definitions.DefinitionError):
        definitions.load_personality(root, "foo")

  def test_lists_personalities(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      write_personality(root, "cfo", cli="codex")
      self.assertEqual(definitions.list_personalities(root), ["ceo", "cfo"])


class EffectiveResolutionTest(unittest.TestCase):
  def test_defaults_apply_when_personality_omits(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")  # model: null, effort: null
      defaults = definitions.load_defaults(root)
      p = definitions.load_personality(root, "ceo")
      cfg = definitions.resolve_effective(defaults, p)
      self.assertEqual(cfg.model, "claude-sonnet-4-6")
      self.assertIsNone(cfg.effort)

  def test_defaults_apply_codex_effort(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "cfo", cli="codex")
      defaults = definitions.load_defaults(root)
      p = definitions.load_personality(root, "cfo")
      cfg = definitions.resolve_effective(defaults, p)
      self.assertEqual(cfg.model, "gpt-5.5")
      self.assertEqual(cfg.effort, "low")

  def test_personality_overrides_defaults(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(
        root, "cto", cli="copilot",
        model="\"gpt-5.4-special\"",
        effort="\"high\"",
      )
      defaults = definitions.load_defaults(root)
      p = definitions.load_personality(root, "cto")
      cfg = definitions.resolve_effective(defaults, p)
      self.assertEqual(cfg.model, "gpt-5.4-special")
      self.assertEqual(cfg.effort, "high")

  def test_cli_override_at_call_site(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = make_repo(pathlib.Path(tmp))
      write_personality(root, "ceo", cli="claude")
      defaults = definitions.load_defaults(root)
      p = definitions.load_personality(root, "ceo")
      cfg = definitions.resolve_effective(
        defaults, p, model_override="claude-opus-4-7", effort_override="high",
      )
      self.assertEqual(cfg.model, "claude-opus-4-7")
      self.assertEqual(cfg.effort, "high")


if __name__ == "__main__":
  unittest.main()
