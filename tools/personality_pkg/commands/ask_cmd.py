"""`personality ask <name> "<prompt>"` — one-shot non-interactive ask.

Contract (`./repo.sh personality ask`):
  - stdout: only the target's reply.
  - stderr: lock waits, replay notices, adapter errors.
  - exit 0: stdout usable as reply.
  - exit 2: invalid args / missing personality.
  - exit 3: lock acquisition failed/timed out.
  - exit 4: backing CLI unavailable or non-zero return.
  - exit 5: transcript/state corruption.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Callable, TextIO, Sequence

from tools.personality_pkg import (
  claude_adapter, codex_adapter, copilot_adapter, definitions, runner, state,
  transcript,
)


EXIT_OK = 0
EXIT_BAD_ARGS = 2
EXIT_LOCK = 3
EXIT_CLI = 4
EXIT_CORRUPT = 5


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="personality ask")
  p.add_argument("name")
  p.add_argument("prompt", nargs="?",
                 help="prompt text; pass `-` to read from stdin")
  p.add_argument("--caller", default=None)
  p.add_argument("--json", dest="emit_json", action="store_true")
  p.add_argument("--replay", action="store_true",
                 help="force transcript-replay fallback even if a session_id exists")
  p.add_argument("--no-native-resume", action="store_true",
                 help="alias for --replay")
  p.add_argument("--lock-mode", choices=("fail", "wait"), default=None)
  p.add_argument("--lock-timeout", type=float, default=None)
  p.add_argument("--model", default=None)
  p.add_argument("--effort", default=None)
  return p


def _now_iso() -> str:
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


AskInvocation = (
  claude_adapter.Invocation | codex_adapter.Invocation | copilot_adapter.Invocation
)


def _resolve_prompt(args: argparse.Namespace, in_stream: TextIO) -> str | None:
  prompt = args.prompt
  if prompt is None:
    return None
  if prompt == "-":
    return in_stream.read().rstrip("\n")
  return str(prompt)


def _build_adapter_invocation(
  cfg: definitions.EffectiveConfig,
  *,
  session_id: str | None,
  prompt_for_cli: str,
  use_replay: bool,
  repo_root: pathlib.Path,
  state_dir: pathlib.Path,
) -> AskInvocation:
  if cfg.cli == "claude":
    return claude_adapter.ask_argv(
      cfg, session_id=session_id, prompt=prompt_for_cli, use_replay=use_replay,
    )
  if cfg.cli == "codex":
    return codex_adapter.ask_argv(
      cfg,
      session_id=session_id,
      prompt=prompt_for_cli,
      use_replay=use_replay,
      repo_root=repo_root,
      last_message_path=state_dir / "last_message.txt",
    )
  if cfg.cli == "copilot":
    return copilot_adapter.ask_argv(
      cfg, session_id=session_id, prompt=prompt_for_cli, use_replay=use_replay,
    )
  raise definitions.DefinitionError(f"unsupported cli {cfg.cli!r}")


def _classify_resume_failure(rc: int, stderr: str) -> bool:
  """Heuristic: treat clear `not found / invalid session` errors as
  recoverable so we can replay-fallback.
  """
  if rc == 0:
    return False
  text = (stderr or "").lower()
  for needle in ("not found", "invalid session", "no such session",
                 "session does not exist", "session expired"):
    if needle in text:
      return True
  return False


def _extract_reply(
  cfg: definitions.EffectiveConfig, result: runner.RunResult,
  *, last_message_path: pathlib.Path | None,
) -> tuple[str, str | None]:
  if cfg.cli == "claude":
    return claude_adapter.parse_ask_response(result.stdout)
  if cfg.cli == "codex":
    if last_message_path is not None:
      msg = codex_adapter.read_last_message(last_message_path)
      if msg:
        return msg, None
    return result.stdout.strip(), None
  if cfg.cli == "copilot":
    return result.stdout.strip(), None
  return result.stdout.strip(), None


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  cli_runner: runner.Runner | None = None,
  out: TextIO = sys.stdout,
  err: TextIO = sys.stderr,
  in_stream: TextIO = sys.stdin,
  now_iso: Callable[[], str] = _now_iso,
) -> int:
  cli_runner = cli_runner or runner.default_runner
  prompt = _resolve_prompt(args, in_stream)
  if not prompt:
    err.write("personality ask: prompt is required (or pass `-` to read stdin)\n")
    return EXIT_BAD_ARGS
  try:
    defaults = definitions.load_defaults(repo_root)
    personality = definitions.load_personality(repo_root, args.name)
  except definitions.DefinitionError as exc:
    err.write(f"personality ask: {exc}\n")
    return EXIT_BAD_ARGS
  cfg = definitions.resolve_effective(
    defaults, personality, model_override=args.model, effort_override=args.effort,
  )
  lock_mode = args.lock_mode or defaults.lock.get("ask_default_mode") or "wait"
  if lock_mode not in {"fail", "wait"}:
    lock_mode = "wait"
  lock_timeout = args.lock_timeout
  if lock_timeout is None:
    raw_timeout = defaults.lock.get("timeout") or "300s"
    if isinstance(raw_timeout, str) and raw_timeout.endswith("s"):
      lock_timeout = float(raw_timeout[:-1])
    elif isinstance(raw_timeout, (int, float)):
      lock_timeout = float(raw_timeout)
    else:
      lock_timeout = 300.0

  state.ensure_state_dir(repo_root, args.name)
  sdir = state.state_dir(repo_root, args.name)

  try:
    with state.acquire_lock(
      repo_root, args.name,
      mode="ask",
      command=f"personality ask {args.name}",
      lock_mode=lock_mode,
      timeout=lock_timeout,
    ):
      return _ask_inside_lock(
        args=args, cfg=cfg, repo_root=repo_root, prompt=prompt,
        cli_runner=cli_runner, sdir=sdir, out=out, err=err,
        defaults=defaults, now_iso=now_iso,
      )
  except state.LockBusy as exc:
    err.write(f"personality ask: lock busy: {exc}\n")
    return EXIT_LOCK
  except state.LockTimeout as exc:
    err.write(f"personality ask: lock timeout: {exc}\n")
    return EXIT_LOCK


def _ask_inside_lock(
  *,
  args: argparse.Namespace,
  cfg: definitions.EffectiveConfig,
  repo_root: pathlib.Path,
  prompt: str,
  cli_runner: runner.Runner,
  sdir: pathlib.Path,
  out: TextIO,
  err: TextIO,
  defaults: definitions.Defaults,
  now_iso: Callable[[], str],
) -> int:
  meta = state.read_session_meta(repo_root, cfg.name)
  replay_required = bool(meta.get("replay_required"))
  forced_replay = args.replay or args.no_native_resume or replay_required
  session_id = state.read_session_id(repo_root, cfg.name) if not args.replay else None
  use_replay = forced_replay or session_id is None

  # Append the user prompt eagerly; replay-prompt building reads the
  # transcript for context but does not include the brand-new user turn
  # twice.
  transcript.append_entry(repo_root, cfg.name, {
    "kind": "user", "source": "ask", "content": prompt,
  }, now_iso=now_iso)

  prior_entries = transcript.read_entries(repo_root, cfg.name)
  # Drop the just-appended user entry from the replay-context view; it is
  # the "new prompt", not prior context.
  prior_for_replay = prior_entries[:-1] if prior_entries else []
  if not any(e.get("kind") == "role" for e in prior_for_replay):
    transcript.append_entry(repo_root, cfg.name, {
      "kind": "role",
      "definition_sha256": cfg.definition_sha256,
      "content": cfg.body,
    }, now_iso=now_iso)
    prior_for_replay = transcript.read_entries(repo_root, cfg.name)[:-1]

  prompt_for_cli = prompt
  if use_replay:
    replay_text = transcript.build_replay_prompt(
      role_body=cfg.body,
      entries=prior_for_replay,
      new_prompt=prompt,
      max_turns=int(defaults.replay.get("max_turns") or 40),
      max_bytes=int(defaults.replay.get("max_bytes") or 200_000),
    )
    (sdir / "replay_prompt.md").write_text(replay_text, encoding="utf-8")
    prompt_for_cli = replay_text

  invocation = _build_adapter_invocation(
    cfg, session_id=session_id, prompt_for_cli=prompt_for_cli,
    use_replay=use_replay, repo_root=repo_root, state_dir=sdir,
  )

  result = cli_runner(invocation.argv)

  # Native resume failed in a recoverable way → replay fallback.
  if invocation.used_native_resume and _classify_resume_failure(result.rc, result.stderr):
    err.write(
      f"personality ask: native resume for {cfg.name!r} failed; replaying transcript\n"
    )
    transcript.append_entry(repo_root, cfg.name, {
      "kind": "error", "cli": cfg.cli, "recoverable": True,
      "content": "native resume failed; replay used",
    }, now_iso=now_iso)
    state.clear_session_id(repo_root, cfg.name)
    fallback_text = transcript.build_replay_prompt(
      role_body=cfg.body,
      entries=transcript.read_entries(repo_root, cfg.name)[:-2],
      new_prompt=prompt,
      max_turns=int(defaults.replay.get("max_turns") or 40),
      max_bytes=int(defaults.replay.get("max_bytes") or 200_000),
    )
    (sdir / "replay_prompt.md").write_text(fallback_text, encoding="utf-8")
    fallback = _build_adapter_invocation(
      cfg, session_id=None, prompt_for_cli=fallback_text,
      use_replay=True, repo_root=repo_root, state_dir=sdir,
    )
    result = cli_runner(fallback.argv)
    invocation = fallback
    use_replay = True

  (sdir / "last_stdout.txt").write_text(result.stdout, encoding="utf-8")
  (sdir / "last_stderr.txt").write_text(result.stderr, encoding="utf-8")

  if result.rc != 0:
    err.write(
      f"personality ask: backing CLI {cfg.cli!r} returned rc={result.rc}\n"
    )
    if result.stderr:
      err.write(result.stderr)
      if not result.stderr.endswith("\n"):
        err.write("\n")
    transcript.append_entry(repo_root, cfg.name, {
      "kind": "error", "cli": cfg.cli, "recoverable": False,
      "content": f"cli rc={result.rc}",
    }, now_iso=now_iso)
    return EXIT_CLI

  last_message_path = (
    invocation.last_message_path
    if isinstance(invocation, codex_adapter.Invocation)
    else None
  )
  reply, new_session_id = _extract_reply(
    cfg, result, last_message_path=last_message_path,
  )
  transcript.append_entry(repo_root, cfg.name, {
    "kind": "assistant",
    "cli": cfg.cli,
    "session_id": new_session_id or state.read_session_id(repo_root, cfg.name),
    "content": reply,
  }, now_iso=now_iso)
  if new_session_id:
    state.write_session_id(repo_root, cfg.name, new_session_id)
  state.write_session_meta(repo_root, cfg.name, {
    "cli": cfg.cli,
    "session_id": new_session_id or state.read_session_id(repo_root, cfg.name) or "",
    "created_at": (
      (state.read_session_meta(repo_root, cfg.name) or {}).get("created_at")
      or now_iso()
    ),
    "updated_at": now_iso(),
    "native_resume": bool(invocation.used_native_resume),
    "replay_required": bool(use_replay and not invocation.used_native_resume and result.rc == 0 and not new_session_id),
    "definition_sha256": cfg.definition_sha256,
    "defaults_sha256": cfg.defaults_sha256,
  })
  state.write_last_invocation(repo_root, cfg.name, {
    "argv": list(invocation.argv),
    "used_native_resume": bool(invocation.used_native_resume),
    "used_replay": bool(use_replay),
    "rc": result.rc,
    "ts": now_iso(),
  })

  if args.emit_json:
    out.write(json.dumps({
      "name": cfg.name,
      "cli": cfg.cli,
      "model": cfg.model,
      "effort": cfg.effort,
      "used_native_resume": bool(invocation.used_native_resume),
      "used_replay": bool(use_replay),
      "reply": reply,
    }, indent=2) + "\n")
  else:
    out.write(reply)
    if not reply.endswith("\n"):
      out.write("\n")
  return EXIT_OK


def main(argv: Sequence[str] | None, *, repo_root: pathlib.Path,
         cli_runner: runner.Runner | None = None) -> int:
  args = build_parser().parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root, cli_runner=cli_runner)
