"""Interactive `infra provision-hetzner`.

Hetzner token stays on operator machine. Cloud-init receives only SSH
key source, host tuning, seed list, and host-local WG key generation.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Callable, Sequence

from tools.infra_pkg import gh, identity, inventory, tuning, units_render, wg


Runner = Callable[..., subprocess.CompletedProcess[str]]
InputFn = Callable[[str], str]


def _ok(msg: str) -> None:
  print(f"infra: {msg}")


def _err(msg: str) -> None:
  print(f"infra: {msg}", file=sys.stderr)


def _provider_script(repo_root: pathlib.Path) -> pathlib.Path:
  return repo_root / "bootstrap" / "providers" / "hetzner.sh"


def _run(
  argv: list[str],
  *,
  runner: Runner = subprocess.run,
  input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
  return runner(
    argv,
    input=input_text,
    text=True,
    capture_output=True,
    check=False,
  )


def provider_lines(
  repo_root: pathlib.Path,
  args: list[str],
  *,
  runner: Runner = subprocess.run,
) -> list[str]:
  proc = _run([str(_provider_script(repo_root)), *args], runner=runner)
  if proc.returncode != 0:
    raise SystemExit(f"infra: hetzner provider failed: {proc.stderr.strip() or proc.returncode}")
  return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _prompt_default(prompt: str, default: str, input_fn: InputFn = input) -> str:
  suffix = f" [{default}]" if default else ""
  raw = input_fn(f"{prompt}{suffix}: ").strip()
  return raw or default


def _prompt_choice(
  prompt: str,
  choices: Sequence[str],
  default: str,
  input_fn: InputFn = input,
) -> str:
  if not choices:
    raise SystemExit(f"infra: no choices for {prompt}")
  if default not in choices:
    default = choices[0]
  print(f"infra: {prompt} choices: {', '.join(choices)}")
  while True:
    value = _prompt_default(prompt, default, input_fn=input_fn)
    if value in choices:
      return value
    _err(f"bad {prompt}: {value!r}")


def _parse_seed_list(raw: str) -> list[str]:
  raw = raw.strip()
  if not raw or raw.lower() in {"you are seed", "seed", "self"}:
    return []
  return [part.strip() for part in raw.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog="infra provision-hetzner",
    description="Create Hetzner Cloud node and record it in inventory.",
  )
  p.add_argument("--arch", choices=("arm64", "amd64"), default=None)
  p.add_argument("--region", default=None)
  p.add_argument("--type", dest="server_type", default=None)
  p.add_argument("--cluster-id", type=int, default=None)
  p.add_argument("--node-id", type=int, default=None)
  p.add_argument("--seeds", default=None, help="comma-separated seed list; empty means you are seed")
  p.add_argument("--ssh-key-id", default="-", help="Hetzner SSH key id/name; '-' omits API ssh_keys")
  p.add_argument("--ssh-pubkey-path", default=None, help="local pubkey installed into root authorized_keys")
  p.add_argument("--ssh-keys-github", default=None, metavar="LOGIN")
  p.add_argument("--ssh-keys", default=None, metavar="PATH", help="alias for --ssh-pubkey-path")
  p.add_argument("--smt", choices=("disable", "leave"), default="leave")
  p.add_argument("--name", default=None)
  p.add_argument("--no-ssh-wait", action="store_true")
  return p


def collect_config(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  input_fn: InputFn = input,
  runner: Runner = subprocess.run,
  url_opener=None,
) -> dict:
  arch = args.arch or _prompt_default("arch", "arm64", input_fn=input_fn)
  if arch not in {"arm64", "amd64"}:
    raise SystemExit("infra: arch must be arm64 or amd64")
  if arch == "amd64":
    _ok("consider Contabo via adopt for x86 (#3)")

  regions = provider_lines(repo_root, ["region_list"], runner=runner)
  region = args.region or _prompt_choice("region", regions, regions[0], input_fn=input_fn)
  sizes = provider_lines(repo_root, ["size_list", f"--arch={arch}"], runner=runner)
  server_type = args.server_type or _prompt_choice(
    "instance type", sizes, "cax11" if arch == "arm64" and "cax11" in sizes else sizes[0],
    input_fn=input_fn,
  )
  cluster_id = args.cluster_id
  if cluster_id is None:
    cluster_id = int(_prompt_default("cluster_id", "1", input_fn=input_fn))
  node_id = args.node_id
  if node_id is None:
    node_id = int(_prompt_default("node_id", "1", input_fn=input_fn))
  identity.validate_cluster_id(cluster_id)
  identity.validate_node_id(node_id)

  seeds = _parse_seed_list(
    args.seeds if args.seeds is not None
    else _prompt_default("seed list (comma-separated, or 'you are seed')", "you are seed", input_fn=input_fn)
  )
  ssh_pubkey_path = args.ssh_keys or args.ssh_pubkey_path
  if ssh_pubkey_path is None and args.ssh_keys_github is None:
    prompted = _prompt_default("SSH pubkey path (blank = GitHub keys)", "", input_fn=input_fn)
    ssh_pubkey_path = prompted or None
  if ssh_pubkey_path and args.ssh_keys_github:
    raise SystemExit("infra: --ssh-keys/--ssh-pubkey-path and --ssh-keys-github are mutually exclusive")

  login = ""
  pubkey_body = ""
  if ssh_pubkey_path:
    pubkey_body = pathlib.Path(ssh_pubkey_path).read_text(encoding="utf-8").strip() + "\n"
  else:
    login = gh.discover_login(
      override=args.ssh_keys_github,
      opener=url_opener or __import__("urllib.request", fromlist=["urlopen"]).urlopen,
    )
    _ok(f"github login resolved: {login}")

  name = args.name or f"node-{node_id}-c{cluster_id}"
  return {
    "arch": arch,
    "region": region,
    "server_type": server_type,
    "cluster_id": cluster_id,
    "node_id": node_id,
    "seeds": seeds,
    "ssh_key_id": args.ssh_key_id,
    "ssh_pubkey_path": ssh_pubkey_path or "",
    "ssh_pubkey_body": pubkey_body,
    "login_for_keys_sync": login,
    "smt": args.smt,
    "name": name,
  }


def _indent_block(body: str, spaces: int = 6) -> str:
  pad = " " * spaces
  return "".join(f"{pad}{line}\n" for line in body.splitlines())


def _yaml_cmd(cmd: str) -> str:
  return f"  - [ bash, -lc, {json.dumps(cmd)} ]"


def render_cloud_init(config: dict) -> str:
  cluster_id = int(config["cluster_id"])
  seeds = "\n".join(config.get("seeds") or []) + ("\n" if config.get("seeds") else "")
  sysctls = tuning.render_sysctl_dropin()
  files: list[tuple[str, str, str]] = [
    ("/etc/sysctl.d/90-infra-fabric.conf", sysctls, "0644"),
    ("/etc/infra/seeds", seeds, "0644"),
  ]
  login = str(config.get("login_for_keys_sync") or "")
  if config.get("ssh_pubkey_body"):
    files.append(("/etc/infra/authorized_keys.seed", str(config["ssh_pubkey_body"]), "0600"))
  else:
    service = units_render.render("gh-keys-sync.service.in", login)
    timer = units_render.render("gh-keys-sync.timer.in", login)
    files.append(("/etc/systemd/system/gh-keys-sync.service", service, "0644"))
    files.append(("/etc/systemd/system/gh-keys-sync.timer", timer, "0644"))

  lines = ["#cloud-config", "package_update: true", "packages:", "  - curl", "  - wireguard-tools", "  - tuned", "write_files:"]
  for path, body, perms in files:
    lines.extend([
      f"  - path: {path}",
      f"    permissions: '{perms}'",
      "    owner: root:root",
      "    content: |",
      _indent_block(body).rstrip("\n"),
    ])

  priv, pub = wg.keypair_paths(cluster_id)
  cmds = [
    "mkdir -p /root/.ssh /etc/infra /etc/wireguard && chmod 0700 /root/.ssh /etc/wireguard",
  ]
  if config.get("ssh_pubkey_body"):
    cmds.append("install -m 0600 -o root -g root /etc/infra/authorized_keys.seed /root/.ssh/authorized_keys")
  else:
    cmds.append("systemctl daemon-reload && systemctl enable --now gh-keys-sync.timer && systemctl start gh-keys-sync.service")
  cmds.extend([
    "sysctl --system",
    "tuned-adm profile network-throughput || true",
    f"if [ ! -s {shlex.quote(priv)} ]; then umask 077; wg genkey | tee {shlex.quote(priv)} >/dev/null; chmod 0600 {shlex.quote(priv)}; chown root:root {shlex.quote(priv)}; wg pubkey < {shlex.quote(priv)} > {shlex.quote(pub)}; chmod 0644 {shlex.quote(pub)}; chown root:root {shlex.quote(pub)}; fi",
  ])
  if config.get("smt") == "disable":
    cmds.append(
      "if lscpu | awk -F: '/Thread\\(s\\) per core/ {gsub(/ /,\"\",$2); exit !($2>1)}'; then "
      "grep -q 'nosmt' /etc/default/grub || sed -i 's|^\\(GRUB_CMDLINE_LINUX_DEFAULT=\"[^\"]*\\)\"|\\1 nosmt\"|' /etc/default/grub; "
      "if command -v update-grub >/dev/null 2>&1; then update-grub; elif command -v grub2-mkconfig >/dev/null 2>&1; then grub2-mkconfig -o /boot/grub2/grub.cfg; fi; "
      "fi"
    )
  cmds.append("reboot")
  lines.append("runcmd:")
  lines.extend(_yaml_cmd(cmd) for cmd in cmds)
  lines.append("")
  return "\n".join(lines)


def create_vm(
  repo_root: pathlib.Path,
  config: dict,
  user_data: str,
  *,
  runner: Runner = subprocess.run,
) -> tuple[str, str]:
  with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as tmp:
    tmp.write(user_data)
    tmp.flush()
    proc = _run(
      [
        str(_provider_script(repo_root)),
        "create_vm",
        str(config["name"]),
        str(config["server_type"]),
        str(config["region"]),
        str(config.get("ssh_key_id") or "-"),
        f"--user-data={tmp.name}",
      ],
      runner=runner,
    )
  if proc.returncode != 0:
    raise SystemExit(f"infra: hetzner create failed: {proc.stderr.strip() or proc.returncode}")
  parts = proc.stdout.strip().split()
  if len(parts) != 2:
    raise SystemExit(f"infra: bad create_vm output: {proc.stdout.strip()!r}")
  return parts[0], parts[1]


def wait_for_ssh_and_pubkey(
  ip: str,
  cluster_id: int,
  *,
  runner: Runner = subprocess.run,
  attempts: int = 30,
  sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
  _, pub = wg.keypair_paths(cluster_id)
  argv = [
    "ssh",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=5",
    "-o", "StrictHostKeyChecking=accept-new",
    f"root@{ip}",
    f"cat {shlex.quote(pub)}",
  ]
  last = ""
  for _ in range(attempts):
    proc = _run(argv, runner=runner)
    if proc.returncode == 0 and proc.stdout.strip():
      return proc.stdout.strip()
    last = proc.stderr.strip() or str(proc.returncode)
    sleep_fn(5)
  raise SystemExit(f"infra: ssh-up/pubkey verify failed: {last}")


def record_inventory(
  repo_root: pathlib.Path,
  config: dict,
  *,
  vm_id: str,
  ipv4: str,
  wg_pubkey: str,
) -> dict:
  host = {
    "provider_label": "hetzner",
    "ssh_target": f"root@{ipv4}",
    "cluster_id": int(config["cluster_id"]),
    "node_id": int(config["node_id"]),
    "arch": "aarch64" if config["arch"] == "arm64" else "x86_64",
    "smt_state": "smt_off_pending_reboot" if config.get("smt") == "disable" else "unknown",
    "login_for_keys_sync": str(config.get("login_for_keys_sync") or ""),
    "seeds": list(config.get("seeds") or []),
    "adopted_at": inventory.now_iso(),
    "last_reachable": True,
    "last_reachable_at": inventory.now_iso(),
    "hetzner_vm_id": str(vm_id),
    "wg_pubkey": wg_pubkey,
    "wg_underlay_endpoint": f"{ipv4}:{wg.DEFAULT_LISTEN_PORT}",
    "wg_listen_port": wg.DEFAULT_LISTEN_PORT,
    "peers": [],
  }
  inventory.upsert(repo_root, host)
  return host


def run(
  args: argparse.Namespace,
  *,
  repo_root: pathlib.Path,
  input_fn: InputFn = input,
  runner: Runner = subprocess.run,
  url_opener=None,
  sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
  config = collect_config(
    args, repo_root=repo_root, input_fn=input_fn, runner=runner, url_opener=url_opener,
  )
  user_data = render_cloud_init(config)
  vm_id, ipv4 = create_vm(repo_root, config, user_data, runner=runner)
  wg_pubkey = ""
  if not args.no_ssh_wait:
    wg_pubkey = wait_for_ssh_and_pubkey(
      ipv4, int(config["cluster_id"]), runner=runner, sleep_fn=sleep_fn,
    )
  host = record_inventory(
    repo_root, config, vm_id=vm_id, ipv4=ipv4, wg_pubkey=wg_pubkey,
  )
  print(
    "cluster={cluster} node={node} arch={arch} wg_pub={wg_pub} underlay_ip={ip}".format(
      cluster=host["cluster_id"],
      node=host["node_id"],
      arch=config["arch"],
      wg_pub=wg_pubkey,
      ip=ipv4,
    )
  )
  return 0


def main(argv: Sequence[str] | None = None, *, repo_root: pathlib.Path) -> int:
  parser = build_parser()
  args = parser.parse_args(list(argv) if argv is not None else None)
  return run(args, repo_root=repo_root)
