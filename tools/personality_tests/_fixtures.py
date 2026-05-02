"""Shared fixtures for personality tests.

Builds an isolated repo-shaped tree under a temp dir so tests never
touch the real `.local/personalities/` or `.agents/personalities/`.
"""
from __future__ import annotations

import pathlib
import textwrap


DEFAULTS_YAML = textwrap.dedent(
  """\
  schema_version: 1
  defaults:
    claude:
      command: claude
      model: claude-sonnet-4-6
      effort: null
    codex:
      command: codex
      model: gpt-5.5
      effort: low
    copilot:
      command: copilot
      model: gpt-5.4
      effort: null
  lock:
    ask_default_mode: wait
    as_root_default_mode: fail
    timeout: 300s
    stale_after: 12h
  replay:
    max_turns: 40
    max_bytes: 200000
    drift_policy: refresh-and-continue
  """
)


def make_repo(root: pathlib.Path) -> pathlib.Path:
  (root / ".agents/personalities").mkdir(parents=True, exist_ok=True)
  (root / ".agents/personalities/_defaults.yaml").write_text(
    DEFAULTS_YAML, encoding="utf-8"
  )
  (root / ".local/personalities").mkdir(parents=True, exist_ok=True)
  return root


def write_personality(
  root: pathlib.Path, name: str, *,
  cli: str = "claude",
  title: str | None = None,
  model: str = "null",
  effort: str = "null",
  delegates: list[str] | None = None,
  body: str = "Test role body.",
) -> pathlib.Path:
  delegates = delegates or []
  delegate_block = "\n".join(f"  - {d}" for d in delegates) or "  []"
  if not delegates:
    delegates_yaml = "delegates_to: []"
  else:
    delegates_yaml = "delegates_to:\n" + "\n".join(f"  - {d}" for d in delegates)
  text = textwrap.dedent(
    f"""\
    ---
    name: {name}
    title: {title or name.upper()}
    cli: {cli}
    model: {model}
    effort: {effort}
    mode: interactive
    {delegates_yaml}
    tools:
      shell_allowlist:
        - "./repo.sh personality ask *"
    clear_policy: state-only
    ---

    {body}
    """
  )
  pdir = root / ".agents/personalities" / name
  pdir.mkdir(parents=True, exist_ok=True)
  path = pdir / "personality.md"
  path.write_text(text, encoding="utf-8")
  return path
