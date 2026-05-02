"""Per-machine personality session state.

Layout (gitignored under `.local/`):

  .local/personalities/<name>/
    session_id          # native CLI session UUID, one line, no decoration
    session_meta.yaml   # adapter + creation metadata
    transcript.jsonl    # helper-owned durable exchange log
    lock                # advisory file lock + diagnostic metadata
    last_invocation.json
    last_stdout.txt
    last_stderr.txt
    replay_prompt.md

The lock semantics follow the spec:
- `as-root` defaults to fail-fast, `ask` defaults to wait.
- Acquired before reading any state, released only after state is durably
  flushed.
- We use `fcntl.flock` for portability; metadata about the lock holder is
  written into the lock file itself.
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
import pathlib
import shutil
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator


STATE_BASE_REL = ".local/personalities"


def _now_iso() -> str:
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_dir(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return repo_root / STATE_BASE_REL / name


def ensure_state_dir(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  d = state_dir(repo_root, name)
  d.mkdir(parents=True, exist_ok=True)
  return d


def session_id_path(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return state_dir(repo_root, name) / "session_id"


def transcript_path(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return state_dir(repo_root, name) / "transcript.jsonl"


def session_meta_path(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return state_dir(repo_root, name) / "session_meta.yaml"


def lock_path(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return state_dir(repo_root, name) / "lock"


def last_invocation_path(repo_root: pathlib.Path, name: str) -> pathlib.Path:
  return state_dir(repo_root, name) / "last_invocation.json"


# ---- session_id ------------------------------------------------------------


def read_session_id(repo_root: pathlib.Path, name: str) -> str | None:
  path = session_id_path(repo_root, name)
  if not path.exists():
    return None
  raw = path.read_text(encoding="utf-8").strip()
  return raw or None


def write_session_id(repo_root: pathlib.Path, name: str, sid: str) -> None:
  ensure_state_dir(repo_root, name)
  session_id_path(repo_root, name).write_text(
    sid.strip() + "\n", encoding="utf-8"
  )


def clear_session_id(repo_root: pathlib.Path, name: str) -> None:
  path = session_id_path(repo_root, name)
  try:
    path.unlink()
  except FileNotFoundError:
    pass


# ---- session_meta.yaml -----------------------------------------------------


def write_session_meta(
  repo_root: pathlib.Path, name: str, meta: dict[str, Any]
) -> None:
  ensure_state_dir(repo_root, name)
  ordered_keys = (
    "cli", "session_id", "created_at", "updated_at",
    "native_resume", "replay_required",
    "definition_sha256", "defaults_sha256",
  )
  lines = []
  for key in ordered_keys:
    if key not in meta:
      continue
    val = meta[key]
    if val is None:
      lines.append(f"{key}: null")
    elif isinstance(val, bool):
      lines.append(f"{key}: {'true' if val else 'false'}")
    elif isinstance(val, str):
      lines.append(f'{key}: "{val}"')
    else:
      lines.append(f"{key}: {val}")
  session_meta_path(repo_root, name).write_text(
    "\n".join(lines) + "\n", encoding="utf-8"
  )


def read_session_meta(repo_root: pathlib.Path, name: str) -> dict[str, Any]:
  from tools.personality_pkg.definitions import parse_yaml_minimal
  path = session_meta_path(repo_root, name)
  if not path.exists():
    return {}
  data = parse_yaml_minimal(path.read_text(encoding="utf-8"))
  return data if isinstance(data, dict) else {}


# ---- last invocation -------------------------------------------------------


def write_last_invocation(
  repo_root: pathlib.Path, name: str, payload: dict[str, Any]
) -> None:
  ensure_state_dir(repo_root, name)
  last_invocation_path(repo_root, name).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )


# ---- lock ------------------------------------------------------------------


@dataclass
class LockHandle:
  fd: int
  path: pathlib.Path
  metadata: dict[str, Any]


class LockBusy(RuntimeError):
  """Lock is held; raised when fail-fast mode is requested."""


class LockTimeout(RuntimeError):
  """Wait mode timed out before acquiring the lock."""


def _format_lock_metadata(metadata: dict[str, Any]) -> str:
  ordered_keys = ("pid", "host", "mode", "started_at", "command")
  lines = []
  for key in ordered_keys:
    if key not in metadata:
      continue
    val = metadata[key]
    if isinstance(val, str):
      lines.append(f'{key}: "{val}"')
    else:
      lines.append(f"{key}: {val}")
  return "\n".join(lines) + "\n"


def parse_lock_metadata(text: str) -> dict[str, Any]:
  from tools.personality_pkg.definitions import parse_yaml_minimal
  data = parse_yaml_minimal(text)
  return data if isinstance(data, dict) else {}


def _try_acquire(fd: int) -> bool:
  try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return True
  except OSError as exc:
    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
      return False
    raise


@contextmanager
def acquire_lock(
  repo_root: pathlib.Path,
  name: str,
  *,
  mode: str,
  command: str,
  lock_mode: str = "wait",
  timeout: float = 300.0,
  poll_interval: float = 0.1,
  now_iso: Callable[[], str] = _now_iso,
) -> Iterator[LockHandle]:
  """Acquire the per-personality lock.

  `lock_mode`:
    - `"fail"` raises LockBusy immediately if the lock is held.
    - `"wait"` polls until acquired or `timeout` seconds elapse.
  """
  if lock_mode not in {"fail", "wait"}:
    raise ValueError(f"lock_mode must be `fail` or `wait`, got {lock_mode!r}")
  ensure_state_dir(repo_root, name)
  path = lock_path(repo_root, name)
  fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
  acquired = False
  try:
    if lock_mode == "fail":
      acquired = _try_acquire(fd)
      if not acquired:
        existing = ""
        try:
          existing = path.read_text(encoding="utf-8")
        except OSError:
          pass
        raise LockBusy(
          f"personality {name!r} lock held; lock file: {path}\n"
          f"holder metadata:\n{existing.strip() or '<unreadable>'}"
        )
    else:
      deadline = time.monotonic() + max(timeout, 0)
      while True:
        if _try_acquire(fd):
          acquired = True
          break
        if time.monotonic() >= deadline:
          existing = ""
          try:
            existing = path.read_text(encoding="utf-8")
          except OSError:
            pass
          raise LockTimeout(
            f"personality {name!r} lock wait timed out after {timeout}s; "
            f"lock file: {path}\nholder metadata:\n"
            f"{existing.strip() or '<unreadable>'}"
          )
        time.sleep(poll_interval)
    metadata = {
      "pid": os.getpid(),
      "host": socket.gethostname(),
      "mode": mode,
      "started_at": now_iso(),
      "command": command,
    }
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, _format_lock_metadata(metadata).encode("utf-8"))
    yield LockHandle(fd=fd, path=path, metadata=metadata)
  finally:
    if acquired:
      try:
        fcntl.flock(fd, fcntl.LOCK_UN)
      except OSError:
        pass
    try:
      os.close(fd)
    except OSError:
      pass


# ---- clear -----------------------------------------------------------------


def clear_state(repo_root: pathlib.Path, name: str) -> bool:
  """Delete `.local/personalities/<name>/` if present.

  Returns True iff something was removed. Definitions under
  `.agents/personalities/<name>/` are never touched.
  """
  d = state_dir(repo_root, name)
  if not d.exists():
    return False
  shutil.rmtree(d)
  return True


# ---- last-active timestamp -------------------------------------------------


def last_active_iso(repo_root: pathlib.Path, name: str) -> str | None:
  meta = read_session_meta(repo_root, name)
  ts = meta.get("updated_at") or meta.get("created_at")
  if isinstance(ts, str) and ts:
    return ts
  tpath = transcript_path(repo_root, name)
  if tpath.exists():
    try:
      return datetime.fromtimestamp(
        tpath.stat().st_mtime, tz=timezone.utc
      ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
      return None
  return None
