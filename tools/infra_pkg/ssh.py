"""SSH helpers for adopt and status.

Thin wrappers around `ssh`. Hard-fail loud if ssh is missing or the
target rejects the probe. Tests inject a mock runner via the `runner`
parameter; production uses subprocess.run.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable


SSH_OPTS: tuple[str, ...] = (
  "-o", "BatchMode=yes",
  "-o", "ConnectTimeout=15",
  "-o", "StrictHostKeyChecking=accept-new",
  "-o", "ServerAliveInterval=15",
)


@dataclass
class SshResult:
  rc: int
  stdout: str
  stderr: str


Runner = Callable[[list[str], str | None], SshResult]


def _default_runner(argv: list[str], stdin: str | None) -> SshResult:
  proc = subprocess.run(
    argv,
    input=stdin,
    text=True,
    capture_output=True,
    check=False,
  )
  return SshResult(rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def ssh_run(
  target: str,
  remote_cmd: str,
  *,
  stdin: str | None = None,
  sudo: bool = False,
  runner: Runner = _default_runner,
) -> SshResult:
  if sudo:
    remote_cmd = f"sudo -n bash -lc {shlex.quote(remote_cmd)}"
  else:
    remote_cmd = f"bash -lc {shlex.quote(remote_cmd)}"
  argv = ["ssh", *SSH_OPTS, target, remote_cmd]
  return runner(argv, stdin)


def scp_write(
  target: str,
  remote_path: str,
  content: str,
  *,
  sudo: bool = True,
  runner: Runner = _default_runner,
) -> SshResult:
  """Write `content` to `remote_path` on `target` via ssh + tee.

  Uses ssh+tee instead of scp so the remote-side mode is controlled
  (umask 077) and no local temp file is needed.
  """
  cmd = (
    f"umask 077 && cat > {shlex.quote(remote_path)} && "
    f"chmod 0644 {shlex.quote(remote_path)}"
  )
  return ssh_run(target, cmd, stdin=content, sudo=sudo, runner=runner)


def probe_root_or_sudo(
  target: str,
  *,
  runner: Runner = _default_runner,
) -> str:
  """Return 'root' or 'sudo'; raise SystemExit if neither works."""
  who = ssh_run(target, "id -u", runner=runner)
  if who.rc != 0:
    raise SystemExit(
      f"infra: ssh probe failed for {target}: {who.stderr.strip() or who.rc}"
    )
  if who.stdout.strip() == "0":
    return "root"
  sudo_test = ssh_run(target, "true", sudo=True, runner=runner)
  if sudo_test.rc == 0:
    return "sudo"
  raise SystemExit(
    f"infra: {target} is neither root nor passwordless-sudo capable"
  )
