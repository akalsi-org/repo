"""Codex CLI adapter.

Builds argv arrays for Codex CLI, per the spec:

  Fresh interactive `as-root`:
    codex -m <model> -c model_reasoning_effort='"<effort>"'
          --cd <REPO_ROOT> <SEED_PROMPT>

  Resume interactive `as-root`:
    codex resume <SESSION_ID> -m <model>
          -c model_reasoning_effort='"<effort>"'

  One-shot `ask`, native resume:
    codex exec -m <model> -c model_reasoning_effort='"<effort>"'
               --cd <REPO_ROOT> -o <LAST_MESSAGE>
               resume <SESSION_ID> <PROMPT_WITH_ROLE_REFRESH>

  One-shot `ask`, fresh or replay fallback:
    codex exec -m <model> -c model_reasoning_effort='"<effort>"'
               --cd <REPO_ROOT> -o <LAST_MESSAGE> <REPLAY_PROMPT>

Codex has no `--system-prompt` flag; role injection is handled by seed
prompt, role-refresh wrapping, and replay prompt.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from tools.personality_pkg.definitions import EffectiveConfig


CLI_NAME = "codex"


@dataclass
class Invocation:
  argv: list[str]
  used_native_resume: bool
  mode: str
  last_message_path: pathlib.Path | None = None


def _model_flags(cfg: EffectiveConfig) -> list[str]:
  argv = ["-m", cfg.model]
  if cfg.effort:
    argv += ["-c", f"model_reasoning_effort='\"{cfg.effort}\"'"]
  return argv


def _role_seed(cfg: EffectiveConfig) -> str:
  return (
    "Role context follows; obey it as session-level instruction.\n\n"
    f"{cfg.body.strip()}\n"
  )


def as_root_argv(
  cfg: EffectiveConfig,
  *,
  session_id: str | None,
  repo_root: pathlib.Path,
  initial_prompt: str | None = None,
) -> Invocation:
  if session_id:
    argv = [cfg.command, "resume", session_id, *_model_flags(cfg)]
    return Invocation(argv=argv, used_native_resume=True, mode="as-root")
  argv = [cfg.command, *_model_flags(cfg), "--cd", str(repo_root)]
  seed = initial_prompt or _role_seed(cfg)
  argv += [seed]
  return Invocation(argv=argv, used_native_resume=False, mode="as-root")


def ask_argv(
  cfg: EffectiveConfig,
  *,
  session_id: str | None,
  prompt: str,
  use_replay: bool,
  repo_root: pathlib.Path,
  last_message_path: pathlib.Path,
) -> Invocation:
  argv = [cfg.command, "exec", *_model_flags(cfg),
          "--cd", str(repo_root),
          "-o", str(last_message_path)]
  used_resume = False
  if session_id and not use_replay:
    argv += ["resume", session_id]
    # Native resume: include a brief role refresh in the prompt.
    payload = (
      f"Role refresh — you are still acting as {cfg.personality.title} "
      f"({cfg.name}). Honor the earlier role-context message. "
      f"Now: {prompt.strip()}"
    )
    argv.append(payload)
    used_resume = True
  else:
    argv.append(prompt)
  return Invocation(
    argv=argv, used_native_resume=used_resume, mode="ask",
    last_message_path=last_message_path,
  )


def read_last_message(path: pathlib.Path) -> str:
  if not path.exists():
    return ""
  return path.read_text(encoding="utf-8").strip()
