#!/usr/bin/env bash
# Hetzner Cloud provider. ADR-0014 provider contract.
#
# Credentials: HETZNER_TOKEN env wins, else ~/hetzner.token mode 0600.
# Token never printed and never sent to hosts.

set -euo pipefail

provider_label="hetzner"
default_region="fsn1"
default_size="cax11"
docs_url="https://docs.hetzner.cloud/"

api_base="${HETZNER_API_BASE:-https://api.hetzner.cloud/v1}"
_tmp_cfg=""
_probed=0

_die() {
  printf 'hetzner: %s\n' "$*" >&2
  exit 1
}

_cleanup() {
  if [ -n "${_tmp_cfg:-}" ] && [ -f "$_tmp_cfg" ]; then
    rm -f "$_tmp_cfg"
  fi
}
trap _cleanup EXIT

_read_token() {
  if [ -n "${HETZNER_TOKEN:-}" ]; then
    printf '%s' "$HETZNER_TOKEN"
    return 0
  fi
  local path="${HOME}/hetzner.token"
  [ -f "$path" ] || _die "no token; set HETZNER_TOKEN or write ~/hetzner.token mode 0600"
  local mode
  mode="$(stat -c '%a' "$path" 2>/dev/null || stat -f '%Lp' "$path")"
  [ "$mode" = "600" ] || _die "$path mode must be 0600"
  local token
  token="$(tr -d '\r\n' < "$path")"
  [ -n "$token" ] || _die "$path empty"
  printf '%s' "$token"
}

_ensure_curl_cfg() {
  if [ -n "$_tmp_cfg" ] && [ -f "$_tmp_cfg" ]; then
    return 0
  fi
  local token
  token="$(_read_token)"
  _tmp_cfg="$(mktemp)"
  chmod 0600 "$_tmp_cfg"
  {
    printf 'header = "Authorization: Bearer %s"\n' "$token"
    printf 'header = "Accept: application/json"\n'
    printf 'max-time = 30\n'
    printf 'silent\n'
    printf 'show-error\n'
    printf 'fail\n'
  } > "$_tmp_cfg"
}

_api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local cfg
  _ensure_curl_cfg
  cfg="$_tmp_cfg"
  if [ "$_probed" = "0" ]; then
    local probe
    if ! probe="$(curl --config "$cfg" "${api_base}/locations")"; then
      _die "token probe failed; create Hetzner Cloud API token with read/write scope, put in ~/hetzner.token mode 0600 or HETZNER_TOKEN"
    fi
    _probed=1
    if [ "$method" = "GET" ] && [ "$path" = "/locations" ] && [ -z "$body" ]; then
      printf '%s' "$probe"
      return 0
    fi
  fi
  if [ -n "$body" ]; then
    curl --config "$cfg" -X "$method" \
      -H "Content-Type: application/json" \
      --data-binary @"$body" \
      "${api_base}${path}" || _die "api call failed: $method $path"
  else
    curl --config "$cfg" -X "$method" "${api_base}${path}" || _die "api call failed: $method $path"
  fi
}

_json_payload() {
  local name="$1"
  local type="$2"
  local region="$3"
  local ssh_key_id="$4"
  local user_data_file="$5"
  python3 - "$name" "$type" "$region" "$ssh_key_id" "$user_data_file" <<'PY'
import json
import pathlib
import sys

name, server_type, region, ssh_key_id, user_data_file = sys.argv[1:]
payload = {
  "name": name,
  "server_type": server_type,
  "location": region,
  "image": "ubuntu-24.04",
  "labels": {"managed_by": "repo-infra", "provider": "hetzner"},
}
if ssh_key_id and ssh_key_id != "-":
  try:
    payload["ssh_keys"] = [int(ssh_key_id)]
  except ValueError:
    payload["ssh_keys"] = [ssh_key_id]
if user_data_file:
  payload["user_data"] = pathlib.Path(user_data_file).read_text(encoding="utf-8")
print(json.dumps(payload, separators=(",", ":")))
PY
}

create_vm() {
  [ "$#" -ge 4 ] || _die "usage: create_vm <name> <type> <region> <ssh_key_id> [--user-data=<file>]"
  local name="$1"
  local type="$2"
  local region="$3"
  local ssh_key_id="$4"
  shift 4
  local user_data_file=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --user-data=*) user_data_file="${1#--user-data=}" ;;
      *) _die "unknown create_vm arg $1" ;;
    esac
    shift
  done
  if [ -n "$user_data_file" ] && [ ! -f "$user_data_file" ]; then
    _die "user-data file missing: $user_data_file"
  fi

  local body
  body="$(mktemp)"
  _json_payload "$name" "$type" "$region" "$ssh_key_id" "$user_data_file" > "$body"
  local response
  response="$(_api POST "/servers" "$body")"
  rm -f "$body"
  python3 -c '
import json
import sys

payload = json.load(sys.stdin)
server = payload.get("server", {})
server_id = server.get("id")
ipv4 = (((server.get("public_net") or {}).get("ipv4") or {}).get("ip") or "")
if server_id is None or not ipv4:
  raise SystemExit("hetzner: create response missing id or ipv4")
print(f"{server_id} {ipv4}")
' <<<"$response"
}

destroy_vm() {
  [ "$#" -eq 1 ] || _die "usage: destroy_vm <vm_id>"
  local vm_id="$1"
  if _api DELETE "/servers/${vm_id}" >/dev/null; then
    return 0
  fi
  return 1
}

list_vms() {
  local response
  response="$(_api GET "/servers")"
  python3 -c '
import json
import sys

payload = json.load(sys.stdin)
out = []
for server in payload.get("servers", []):
  public_net = server.get("public_net") or {}
  ipv4 = (public_net.get("ipv4") or {}).get("ip") or ""
  location = server.get("location") or (server.get("datacenter") or {}).get("location") or {}
  stype = server.get("server_type") or {}
  out.append({
    "id": str(server.get("id", "")),
    "name": server.get("name", ""),
    "ipv4": ipv4,
    "region": location.get("name", ""),
    "size": stype.get("name", ""),
    "provider": "hetzner",
    "status": server.get("status", ""),
  })
print(json.dumps(out, sort_keys=True))
' <<<"$response"
}

region_list() {
  local response
  response="$(_api GET "/locations")"
  python3 -c '
import json
import sys

payload = json.load(sys.stdin)
for loc in payload.get("locations", []):
  name = loc.get("name")
  if name:
    print(name)
' <<<"$response"
}

size_list() {
  local arch="arm64"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --arch=arm64) arch="arm64" ;;
      --arch=amd64) arch="amd64" ;;
      *) _die "unknown size_list arg $1" ;;
    esac
    shift
  done
  local response
  response="$(_api GET "/server_types")"
  HETZNER_SIZE_ARCH="$arch" python3 -c '
import json
import os
import sys

arch = os.environ["HETZNER_SIZE_ARCH"]
payload = json.load(sys.stdin)
names = []
for server_type in payload.get("server_types", []):
  name = str(server_type.get("name", ""))
  if arch == "arm64":
    keep = name.startswith("cax")
  else:
    keep = name.startswith("cx") or name.startswith("ccx")
  if keep:
    names.append(name)
for name in sorted(names):
  print(name)
' <<<"$response"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  [ "$#" -gt 0 ] || _die "usage: $0 <create_vm|destroy_vm|list_vms|region_list|size_list> [args...]"
  cmd="$1"
  shift
  case "$cmd" in
    create_vm|destroy_vm|list_vms|region_list|size_list) "$cmd" "$@" ;;
    *) _die "unknown command $cmd" ;;
  esac
fi
