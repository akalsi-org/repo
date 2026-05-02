"""Local host inventory at .local/infra/inventory.json (gitignored).

Schema: {"hosts": [<host record>, ...]}.

Host record fields:
- provider_label
- ssh_target
- cluster_id, node_id
- arch              (e.g. x86_64, aarch64; populated from uname -m)
- smt_state         ("smt_on", "smt_off_pending_reboot", "unknown")
- login_for_keys_sync ("" if --ssh-keys=<path> was used)
- adopted_at        (ISO 8601 UTC)
- last_reachable_at (ISO 8601 UTC; updated by `infra status`)
- last_reachable    (bool; "" until first probe)
- wg_pubkey         (str; populated by `infra wg-up`. Public material only;
                     the private key lives only on the host at
                     /etc/wireguard/wg-c<cluster>.key mode 0600.)
- wg_underlay_endpoint (str "host:port"; the public endpoint peers dial)
- wg_listen_port    (int; default 51820)
- peers             (list of {cluster_id, node_id, wg_pubkey,
                     wg_underlay_endpoint}; managed by `infra wg-peer-add`)

Schema migration: existing host records without WG fields keep working;
wg-up populates the missing fields lazily on first run.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any


REL_PATH = ".local/infra/inventory.json"


def inventory_path(repo_root: pathlib.Path) -> pathlib.Path:
  return repo_root / REL_PATH


def now_iso() -> str:
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(repo_root: pathlib.Path) -> dict[str, Any]:
  path = inventory_path(repo_root)
  if not path.is_file():
    return {"hosts": []}
  raw = path.read_text(encoding="utf-8").strip()
  if not raw:
    return {"hosts": []}
  data = json.loads(raw)
  if not isinstance(data, dict) or not isinstance(data.get("hosts"), list):
    raise SystemExit(f"infra: bad inventory shape at {path}")
  return data


def save(repo_root: pathlib.Path, data: dict[str, Any]) -> None:
  path = inventory_path(repo_root)
  path.parent.mkdir(parents=True, exist_ok=True)
  serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"
  path.write_text(serialized, encoding="utf-8")


def upsert(repo_root: pathlib.Path, host: dict[str, Any]) -> dict[str, Any]:
  """Insert or replace a host by (cluster_id, node_id)."""
  required = ("provider_label", "ssh_target", "cluster_id", "node_id")
  for field in required:
    if field not in host:
      raise SystemExit(f"infra: host record missing field {field!r}")
  data = load(repo_root)
  hosts = data["hosts"]
  key = (host["cluster_id"], host["node_id"])
  for idx, existing in enumerate(hosts):
    if (existing.get("cluster_id"), existing.get("node_id")) == key:
      hosts[idx] = host
      break
  else:
    hosts.append(host)
  data["hosts"] = sorted(
    hosts,
    key=lambda h: (h.get("cluster_id", 0), h.get("node_id", 0)),
  )
  save(repo_root, data)
  return data


def remove_by_provider_vm_id(
  repo_root: pathlib.Path,
  provider_label: str,
  vm_id: str,
) -> tuple[dict[str, Any], int]:
  """Remove hosts matching provider label + provider-native VM id."""
  data = load(repo_root)
  before = len(data["hosts"])
  data["hosts"] = [
    h for h in data["hosts"]
    if not (
      h.get("provider_label") == provider_label
      and str(h.get("hetzner_vm_id", "")) == str(vm_id)
    )
  ]
  removed = before - len(data["hosts"])
  if removed:
    save(repo_root, data)
  return data, removed
