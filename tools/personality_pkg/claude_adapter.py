"""Claude Code adapter.

Builds argv arrays for Claude Code, per the spec:

  Fresh interactive `as-root`:
    claude --model <model> [--effort <level>]
           --append-system-prompt <ROLE> --name "personality:<name>"

  Resume interactive `as-root`:
    claude --resume <SESSION_ID>
           --append-system-prompt <ROLE> --name "personality:<name>"

  One-shot `ask`, native resume:
    claude --resume <SESSION_ID> --print --output-format json
           --append-system-prompt <ROLE> <PROMPT>

  One-shot `ask`, fresh or replay fallback:
    claude --print --output-format json --model <model>
           [--effort <level>] --append-system-prompt <ROLE> <REPLAY_PROMPT>
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from tools.personality_pkg.definitions import EffectiveConfig


CLI_NAME = "claude"


@dataclass
class Invocation:
  argv: list[str]
  used_native_resume: bool
  mode: str  # "as-root" or "ask"


def _name_tag(name: str) -> str:
  return f"personality:{name}"


def as_root_argv(
  cfg: EffectiveConfig,
  *,
  session_id: str | None,
  initial_prompt: str | None = None,
) -> Invocation:
  argv = [cfg.command]
  used_resume = False
  if session_id:
    argv += ["--resume", session_id]
    used_resume = True
  else:
    argv += ["--model", cfg.model]
    if cfg.effort:
      argv += ["--effort", cfg.effort]
  argv += ["--append-system-prompt", cfg.body]
  argv += ["--name", _name_tag(cfg.name)]
  if initial_prompt:
    argv += [initial_prompt]
  return Invocation(argv=argv, used_native_resume=used_resume, mode="as-root")


def ask_argv(
  cfg: EffectiveConfig,
  *,
  session_id: str | None,
  prompt: str,
  use_replay: bool,
) -> Invocation:
  argv = [cfg.command]
  used_resume = False
  if session_id and not use_replay:
    argv += ["--resume", session_id]
    used_resume = True
  else:
    argv += ["--model", cfg.model]
    if cfg.effort:
      argv += ["--effort", cfg.effort]
  argv += [
    "--print", "--output-format", "json",
    "--append-system-prompt", cfg.body,
    prompt,
  ]
  return Invocation(argv=argv, used_native_resume=used_resume, mode="ask")


def parse_ask_response(stdout: str) -> tuple[str, str | None]:
  """Extract the assistant reply text + a session id from `--output-format json`.

  Claude's `--print --output-format json` payload includes a `result`
  string and a `session_id`. The exact key set may vary across Claude
  versions; we accept the documented fields and tolerate unknown ones.
  Returns (reply_text, session_id_or_None).
  """
  try:
    data = json.loads(stdout)
  except json.JSONDecodeError:
    return stdout.strip(), None
  if isinstance(data, dict):
    reply = data.get("result") or data.get("message") or data.get("text") or ""
    sid = data.get("session_id") or data.get("session") or None
    if isinstance(reply, list):  # tolerate message-block style
      parts = [
        block.get("text", "")
        for block in reply
        if isinstance(block, dict)
      ]
      reply = "\n".join(parts).strip()
    return str(reply).strip(), (sid if isinstance(sid, str) else None)
  return stdout.strip(), None
