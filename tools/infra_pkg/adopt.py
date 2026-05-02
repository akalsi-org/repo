"""Orchestrate `infra adopt`.

Caveman-loud user-facing strings. ADR-0014: SMT default off, GH login
runtime-discovered, no concrete login in tracked files.
"""
from __future__ import annotations

import argparse
import pathlib
import shlex
import sys
from typing import Sequence

from tools.infra_pkg import gh, identity, inventory, lscpu, ssh, tuning, units_render


def _err(msg: str) -> None:
  print(f"infra: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
  print(f"infra: {msg}")


def _provider_known(label: str, repo_root: pathlib.Path) -> bool:
  return (repo_root / "bootstrap" / "providers" / f"{label}.sh").is_file()


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra adopt",
    description="Adopt an SSH-reachable host onto the fabric (ADR-0014).",
  )
  p.add_argument("provider_label", help="provider slug, e.g. contabo")
  p.add_argument("ssh_target", help="user@host or alias")
  p.add_argument("cluster_id", type=int, help="cluster ID 1..255")
  p.add_argument("node_id", type=int, help="node ID 1..65535")
  p.add_argument("seeds", nargs="*", help="seed peer SSH targets (informational; gossip slice lands later)")
  p.add_argument(
    "--smt", choices=("disable", "leave"), default="leave",
    help="disable applies nosmt iff host has >1 thread per core; default leave",
  )
  p.add_argument(
    "--ssh-keys-github", default=None, metavar="LOGIN",
    help="override discovered GitHub login for keys-sync",
  )
  p.add_argument(
    "--ssh-keys", default=None, metavar="PATH",
    help="local pubkey file; disables GH-sync entirely",
  )
  p.add_argument(
    "--keys-sync-interval", default="15min",
    help="systemd OnUnitActiveSec= for the timer (default 15min)",
  )
  p.add_argument(
    "--dry-run", action="store_true",
    help="print actions but issue no SSH commands",
  )
  return p


def _wireguard_probe(target: str, sudo_word: str, runner) -> None:
  res = ssh.ssh_run(target, "modprobe wireguard", sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(
      "infra: wireguard kernel module not loadable on host; "
      "remediate: apt install wireguard-tools  (or distro equivalent) "
      "then re-run infra adopt"
    )


def _apply_smt(target: str, sudo_word: str, runner, smt_disable_opt_in: bool) -> dict:
  res = ssh.ssh_run(target, "lscpu", runner=runner)
  if res.rc != 0:
    raise SystemExit(f"infra: lscpu failed on {target}: {res.stderr.strip() or res.rc}")
  decision = lscpu.smt_decision(res.stdout, smt_disable_opt_in)
  if not decision["apply_nosmt"]:
    _ok(f"smt: skip — {decision['reason']}")
    return decision
  # Mutate /etc/default/grub: add nosmt to GRUB_CMDLINE_LINUX_DEFAULT.
  grub_cmd = (
    "set -e; "
    "f=/etc/default/grub; "
    "grep -q 'nosmt' \"$f\" || "
    "  sed -i 's|^\\(GRUB_CMDLINE_LINUX_DEFAULT=\"[^\"]*\\)\"|\\1 nosmt\"|' \"$f\"; "
    "if command -v update-grub >/dev/null 2>&1; then update-grub; "
    "elif command -v grub2-mkconfig >/dev/null 2>&1; then grub2-mkconfig -o /boot/grub2/grub.cfg; "
    "else echo 'infra: no grub generator found' >&2; exit 1; fi; "
    "shutdown -r +1 'infra adopt scheduled reboot for nosmt'"
  )
  res = ssh.ssh_run(target, grub_cmd, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(f"infra: nosmt apply failed: {res.stderr.strip() or res.rc}")
  _ok("smt: nosmt applied; reboot scheduled in 1 minute")
  return decision


def _apply_sysctls(target: str, sudo_word: str, runner) -> None:
  payload = tuning.render_sysctl_dropin()
  res = ssh.scp_write(target, tuning.SYSCTL_DROPIN_PATH, payload, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(f"infra: sysctl dropin write failed: {res.stderr.strip() or res.rc}")
  reload_res = ssh.ssh_run(target, "sysctl --system", sudo=(sudo_word == "sudo"), runner=runner)
  if reload_res.rc != 0:
    raise SystemExit(f"infra: sysctl --system failed: {reload_res.stderr.strip() or reload_res.rc}")


def _apply_tuned(target: str, sudo_word: str, runner) -> None:
  has_tuned = ssh.ssh_run(target, "command -v tuned-adm >/dev/null", runner=runner)
  if has_tuned.rc == 0:
    res = ssh.ssh_run(
      target, "tuned-adm profile network-throughput",
      sudo=(sudo_word == "sudo"), runner=runner,
    )
    if res.rc != 0:
      raise SystemExit(f"infra: tuned-adm failed: {res.stderr.strip() or res.rc}")
    _ok("tuning: tuned-adm profile network-throughput applied")
    return
  _ok("tuning: no tuned-adm; applying hand-rolled fallback")
  payload = tuning.render_tuned_fallback_dropin()
  res = ssh.scp_write(target, tuning.TUNED_FALLBACK_DROPIN_PATH, payload, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(f"infra: tuned fallback write failed: {res.stderr.strip() or res.rc}")
  reload_res = ssh.ssh_run(target, "sysctl --system", sudo=(sudo_word == "sudo"), runner=runner)
  if reload_res.rc != 0:
    raise SystemExit(f"infra: sysctl --system failed: {reload_res.stderr.strip() or reload_res.rc}")


def _install_authorized_keys(
  target: str, sudo_word: str, runner,
  login: str | None, local_keys_path: str | None,
) -> None:
  if local_keys_path is not None:
    body = pathlib.Path(local_keys_path).read_text(encoding="utf-8")
    cmd = (
      "set -e; mkdir -p /root/.ssh; chmod 0700 /root/.ssh; "
      f"umask 077; cat > /root/.ssh/authorized_keys; "
      "chmod 0600 /root/.ssh/authorized_keys"
    )
    res = ssh.ssh_run(target, cmd, stdin=body, sudo=(sudo_word == "sudo"), runner=runner)
    if res.rc != 0:
      raise SystemExit(f"infra: authorized_keys write failed: {res.stderr.strip() or res.rc}")
    _ok(f"authorized_keys: installed from local {local_keys_path}")
    return

  url = gh.keys_url(login or "")
  cmd = (
    "set -e; mkdir -p /root/.ssh; chmod 0700 /root/.ssh; "
    f"curl --fail --silent --show-error --max-time 15 {shlex.quote(url)} "
    "-o /root/.ssh/authorized_keys.new && "
    "install -m 0600 -o root -g root /root/.ssh/authorized_keys.new "
    "/root/.ssh/authorized_keys && rm -f /root/.ssh/authorized_keys.new"
  )
  res = ssh.ssh_run(target, cmd, sudo=(sudo_word == "sudo"), runner=runner)
  if res.rc != 0:
    raise SystemExit(f"infra: GH keys fetch failed: {res.stderr.strip() or res.rc}")
  _ok(f"authorized_keys: synced from {url}")


def _install_keys_sync_units(
  target: str, sudo_word: str, runner,
  login: str, interval: str,
) -> None:
  service = units_render.render("gh-keys-sync.service.in", login)
  timer = units_render.render("gh-keys-sync.timer.in", login)
  if interval and interval != "15min":
    timer = timer.replace("OnUnitActiveSec=15min", f"OnUnitActiveSec={interval}")
  for path, body in (
    ("/etc/systemd/system/gh-keys-sync.service", service),
    ("/etc/systemd/system/gh-keys-sync.timer", timer),
  ):
    res = ssh.scp_write(target, path, body, sudo=(sudo_word == "sudo"), runner=runner)
    if res.rc != 0:
      raise SystemExit(f"infra: unit write failed for {path}: {res.stderr.strip() or res.rc}")
  enable = ssh.ssh_run(
    target,
    "systemctl daemon-reload && "
    "systemctl enable --now gh-keys-sync.timer",
    sudo=(sudo_word == "sudo"), runner=runner,
  )
  if enable.rc != 0:
    raise SystemExit(f"infra: timer enable failed: {enable.stderr.strip() or enable.rc}")


def _detect_arch(target: str, runner) -> str:
  res = ssh.ssh_run(target, "uname -m", runner=runner)
  if res.rc != 0 or not res.stdout.strip():
    return "unknown"
  return res.stdout.strip()


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  runner: ssh.Runner | None = None,
  url_opener=None,
) -> int:
  runner = runner or ssh._default_runner
  identity.validate_cluster_id(args.cluster_id)
  identity.validate_node_id(args.node_id)
  if not _provider_known(args.provider_label, repo_root):
    raise SystemExit(
      f"infra: unknown provider {args.provider_label!r}; "
      f"add bootstrap/providers/{args.provider_label}.sh first"
    )

  if args.ssh_keys is not None and args.ssh_keys_github is not None:
    raise SystemExit("infra: --ssh-keys and --ssh-keys-github are mutually exclusive")

  resolved_login = ""
  if args.ssh_keys is None:
    resolved_login = gh.discover_login(
      override=args.ssh_keys_github,
      opener=url_opener or __import__("urllib.request", fromlist=["urlopen"]).urlopen,
    )
    _ok(f"github login resolved: {resolved_login}")

  if args.dry_run:
    _ok("dry-run: stop before any SSH command")
    return 0

  sudo_word = ssh.probe_root_or_sudo(args.ssh_target, runner=runner)
  _ok(f"ssh: {args.ssh_target} reachable as {sudo_word}")

  _wireguard_probe(args.ssh_target, sudo_word, runner)
  _ok("wireguard: kernel module loadable")

  smt_decision = _apply_smt(
    args.ssh_target, sudo_word, runner,
    smt_disable_opt_in=(args.smt == "disable"),
  )

  _apply_sysctls(args.ssh_target, sudo_word, runner)
  _ok(f"sysctls: written to {tuning.SYSCTL_DROPIN_PATH} and reloaded")

  _apply_tuned(args.ssh_target, sudo_word, runner)

  _install_authorized_keys(
    args.ssh_target, sudo_word, runner,
    login=resolved_login if args.ssh_keys is None else None,
    local_keys_path=args.ssh_keys,
  )

  if args.ssh_keys is None and resolved_login:
    _install_keys_sync_units(
      args.ssh_target, sudo_word, runner,
      login=resolved_login, interval=args.keys_sync_interval,
    )
    _ok("keys-sync: gh-keys-sync.timer enabled")

  arch = _detect_arch(args.ssh_target, runner)
  smt_state = (
    "smt_off_pending_reboot" if smt_decision.get("apply_nosmt")
    else ("smt_on" if smt_decision.get("threads_per_core") and smt_decision["threads_per_core"] > 1
          else "unknown")
  )
  host = {
    "provider_label": args.provider_label,
    "ssh_target": args.ssh_target,
    "cluster_id": args.cluster_id,
    "node_id": args.node_id,
    "arch": arch,
    "smt_state": smt_state,
    "login_for_keys_sync": resolved_login,
    "seeds": list(args.seeds or []),
    "adopted_at": inventory.now_iso(),
    "last_reachable": True,
    "last_reachable_at": inventory.now_iso(),
  }
  inventory.upsert(repo_root, host)
  _ok(f"inventory: recorded {args.ssh_target} as cluster {args.cluster_id} node {args.node_id}")
  return 0


def main(argv: Sequence[str] | None = None, *, repo_root: pathlib.Path) -> int:
  parser = build_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
