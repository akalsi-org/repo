"""`personality as-root <name>` — open an interactive persistent session.

Acquires the lock (default fail-fast), then exec()'s the backing CLI
with native resume when a session_id is recorded, or with a fresh seed
otherwise. The lock is released by the dispatcher when the wrapper
process exits — but `exec` replaces the dispatcher, so we keep the
foreground convention: the CLI inherits the lock-holding process and
the lock vanishes when that process exits.

Caveat: native session_id capture for `as-root` is CLI-specific and not
exhaustively automated in v1; the helper records the argv used and lets
the operator re-invoke `as-root` to land back in the native session.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import datetime, timezone
from typing import Callable, Protocol, TextIO, Sequence

from tools.personality_pkg import (
  claude_adapter, codex_adapter, copilot_adapter, definitions, runner, state,
)


class InvocationLike(Protocol):
  argv: list[str]
  used_native_resume: bool


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog="personality as-root")
  p.add_argument("name")
  p.add_argument("--fresh", action="store_true",
                 help="ignore any recorded session_id and start a new session")
  p.add_argument("--replay", action="store_true",
                 help="(reserved for parity with ask; ignored for as-root in v1)")
  p.add_argument("--lock-mode", choices=("fail", "wait"), default=None)
  p.add_argument("--lock-timeout", type=float, default=None)
  p.add_argument("--model", default=None)
  p.add_argument("--effort", default=None)
  p.add_argument("initial_prompt", nargs="?", default=None)
  return p


def _now_iso() -> str:
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_invocation(
  cfg: definitions.EffectiveConfig,
  *,
  session_id: str | None,
  repo_root: pathlib.Path,
  initial_prompt: str | None,
) -> InvocationLike:
  if cfg.cli == "claude":
    return claude_adapter.as_root_argv(
      cfg, session_id=session_id, initial_prompt=initial_prompt,
    )
  if cfg.cli == "codex":
    return codex_adapter.as_root_argv(
      cfg, session_id=session_id, repo_root=repo_root,
      initial_prompt=initial_prompt,
    )
  if cfg.cli == "copilot":
    return copilot_adapter.as_root_argv(
      cfg, session_id=session_id, initial_prompt=initial_prompt,
    )
  raise definitions.DefinitionError(f"unsupported cli {cfg.cli!r}")


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  exec_fn: runner.Runner | None = None,
  out: TextIO = sys.stdout,
  err: TextIO = sys.stderr,
  now_iso: Callable[[], str] = _now_iso,
) -> int:
  exec_fn = exec_fn or runner.exec_runner
  try:
    defaults = definitions.load_defaults(repo_root)
    personality = definitions.load_personality(repo_root, args.name)
  except definitions.DefinitionError as exc:
    err.write(f"personality as-root: {exc}\n")
    return 2
  cfg = definitions.resolve_effective(
    defaults, personality, model_override=args.model, effort_override=args.effort,
  )
  lock_mode = args.lock_mode or defaults.lock.get("as_root_default_mode") or "fail"
  if lock_mode not in {"fail", "wait"}:
    lock_mode = "fail"
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
  session_id = None if args.fresh else state.read_session_id(repo_root, args.name)
  invocation = build_invocation(
    cfg, session_id=session_id, repo_root=repo_root,
    initial_prompt=args.initial_prompt,
  )

  # Record the planned invocation before exec-ing — once exec runs,
  # control never returns here.
  state.write_last_invocation(repo_root, args.name, {
    "argv": list(invocation.argv),
    "used_native_resume": bool(invocation.used_native_resume),
    "mode": "as-root",
    "ts": now_iso(),
  })
  state.write_session_meta(repo_root, args.name, {
    "cli": cfg.cli,
    "session_id": session_id or "",
    "created_at": (
      (state.read_session_meta(repo_root, args.name) or {}).get("created_at")
      or now_iso()
    ),
    "updated_at": now_iso(),
    "native_resume": bool(invocation.used_native_resume),
    "replay_required": bool((state.read_session_meta(repo_root, args.name) or {}).get("replay_required")),
    "definition_sha256": cfg.definition_sha256,
    "defaults_sha256": cfg.defaults_sha256,
  })

  # Acquire the lock and hand control to the backing CLI.
  try:
    cm = state.acquire_lock(
      repo_root, args.name,
      mode="as-root",
      command=f"personality as-root {args.name}",
      lock_mode=lock_mode,
      timeout=lock_timeout,
      now_iso=now_iso,
    )
    cm.__enter__()
  except state.LockBusy as exc:
    err.write(f"personality as-root: lock busy: {exc}\n")
    return 3
  except state.LockTimeout as exc:
    err.write(f"personality as-root: lock timeout: {exc}\n")
    return 3
  err.write(
    f"personality as-root: exec {cfg.cli} for {cfg.name!r} "
    f"(native_resume={invocation.used_native_resume})\n"
  )
  exec_fn(invocation.argv)
  err.write("personality as-root: exec returned unexpectedly\n")
  return 4


def main(argv: Sequence[str] | None, *, repo_root: pathlib.Path,
         exec_fn: runner.Runner | None = None) -> int:
  args = build_parser().parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root, exec_fn=exec_fn)
