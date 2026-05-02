"""GitHub Copilot CLI adapter.

Builds argv arrays for Copilot, per the spec:

  Fresh interactive `as-root`:
    copilot --model <model> [--reasoning-effort <level>]
            --name "personality:<name>" -i <SEED_PROMPT>

  Resume interactive `as-root`:
    copilot --resume=<SESSION_ID_OR_NAME> --model <model>

  One-shot `ask`, native resume:
    copilot --resume=<SESSION_ID> --model <model>
            --prompt <PROMPT_WITH_ROLE_REFRESH> --silent

  One-shot `ask`, fresh or replay fallback:
    copilot --model <model> --prompt <REPLAY_PROMPT> --silent

Copilot has no `--system-prompt` flag; role injection is handled by seed
prompt, role-refresh wrapping, and replay prompt.
"""
from __future__ import annotations

from dataclasses import dataclass

from tools.personality_pkg.definitions import EffectiveConfig


CLI_NAME = "copilot"


@dataclass
class Invocation:
  argv: list[str]
  used_native_resume: bool
  mode: str


def _name_tag(name: str) -> str:
  return f"personality:{name}"


def _role_seed(cfg: EffectiveConfig) -> str:
  return (
    "Role context follows; obey it as session-level instruction.\n\n"
    f"{cfg.body.strip()}\n"
  )


def as_root_argv(
  cfg: EffectiveConfig,
  *,
  session_id: str | None,
  initial_prompt: str | None = None,
) -> Invocation:
  if session_id:
    argv = [
      cfg.command,
      f"--resume={session_id}",
      "--model", cfg.model,
    ]
    return Invocation(argv=argv, used_native_resume=True, mode="as-root")
  argv = [cfg.command, "--model", cfg.model]
  if cfg.effort:
    argv += ["--reasoning-effort", cfg.effort]
  argv += ["--name", _name_tag(cfg.name)]
  seed = initial_prompt or _role_seed(cfg)
  argv += ["-i", seed]
  return Invocation(argv=argv, used_native_resume=False, mode="as-root")


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
    argv += [f"--resume={session_id}", "--model", cfg.model]
    payload = (
      f"Role refresh — you are still acting as {cfg.personality.title} "
      f"({cfg.name}). Honor the earlier role-context message. "
      f"Now: {prompt.strip()}"
    )
    argv += ["--prompt", payload, "--silent"]
    used_resume = True
  else:
    argv += ["--model", cfg.model]
    if cfg.effort:
      argv += ["--reasoning-effort", cfg.effort]
    argv += ["--prompt", prompt, "--silent"]
  return Invocation(argv=argv, used_native_resume=used_resume, mode="ask")
