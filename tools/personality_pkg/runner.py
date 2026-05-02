"""Subprocess runner abstraction.

Tests inject a stub runner so no real `claude`/`codex`/`copilot` is
spawned. The default runner uses `subprocess.run` and never goes through
a shell.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class RunResult:
  rc: int
  stdout: str
  stderr: str


Runner = Callable[[Sequence[str]], RunResult]


def default_runner(argv: Sequence[str]) -> RunResult:
  proc = subprocess.run(
    list(argv),
    check=False,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )
  return RunResult(rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def exec_runner(argv: Sequence[str]) -> RunResult:
  """Replace the current process with the target — used for `as-root`.

  Returns no value if it succeeds (the caller is gone). On exec failure
  it raises OSError.
  """
  import os
  os.execvp(argv[0], list(argv))
  raise RuntimeError("exec returned")  # unreachable
