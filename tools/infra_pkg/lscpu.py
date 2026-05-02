"""lscpu output parsing (ADR-0014, host tuning).

Pure parsing of `lscpu` text. No subprocess. The adopt flow runs
`lscpu` over SSH and feeds the captured text here.
"""
from __future__ import annotations

from typing import Any


def threads_per_core(lscpu_out: str) -> int | None:
  """Return Thread(s) per core from lscpu output, or None if missing.

  Tolerates both `Thread(s) per core:` and `Threads per core:` and
  arbitrary whitespace.
  """
  for raw in lscpu_out.splitlines():
    line = raw.strip()
    if not line:
      continue
    lower = line.lower()
    if not lower.startswith(("thread(s) per core", "threads per core")):
      continue
    _, _, value = line.partition(":")
    value = value.strip()
    if not value:
      continue
    try:
      return int(value)
    except ValueError:
      return None
  return None


def smt_decision(lscpu_out: str, smt_disable_opt_in: bool) -> dict[str, Any]:
  """Return a small decision record describing whether to apply nosmt.

  Output shape:
    {"apply_nosmt": bool, "reason": str, "threads_per_core": int|None}
  """
  tpc = threads_per_core(lscpu_out)
  if tpc is None:
    return {
      "apply_nosmt": False,
      "reason": "lscpu missing Thread(s) per core; skip nosmt",
      "threads_per_core": None,
    }
  if not smt_disable_opt_in:
    return {
      "apply_nosmt": False,
      "reason": "operator did not pass --smt=disable; leave SMT alone",
      "threads_per_core": tpc,
    }
  if tpc < 2:
    return {
      "apply_nosmt": False,
      "reason": "host reports 1 thread per core; nosmt is a no-op",
      "threads_per_core": tpc,
    }
  return {
    "apply_nosmt": True,
    "reason": "operator opted in and host has SMT siblings",
    "threads_per_core": tpc,
  }
