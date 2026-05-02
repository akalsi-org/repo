#!/usr/bin/env bash
# Contabo provider — label-only stub.
#
# This slice (issue #3) only needs Contabo as an inventory label so
# operators can adopt an existing Contabo VPS via tools/infra/adopt.sh
# over plain SSH. No API calls happen here. The real CRUD surface
# (create_vm/destroy_vm/list_vms/region_list/size_list) lands in a
# later issue once the WG underlay + VXLAN overlay slices are merged.
#
# Credential path (when the API impl arrives): ~/contabo.token,
# mode 0600.
#
# Docs: https://api.contabo.com/

set -euo pipefail

provider_label="contabo"
default_region="EU"
default_size="VPS-S"
docs_url="https://api.contabo.com/"

_contabo_todo() {
  local fn="$1"
  printf 'contabo: %s not implemented in this slice\n' "$fn" >&2
  printf 'contabo: use tools/infra/adopt.sh against an existing host\n' >&2
  return 1
}

create_vm()    { _contabo_todo create_vm; }
destroy_vm()   { _contabo_todo destroy_vm; }
list_vms()     { _contabo_todo list_vms; }
region_list()  { _contabo_todo region_list; }
size_list()    { _contabo_todo size_list; }
