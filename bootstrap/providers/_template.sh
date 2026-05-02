#!/usr/bin/env bash
# Provider template — DO NOT source at runtime.
#
# Copy this file to bootstrap/providers/<name>.sh and fill in the
# bodies. The fabric (ADR-0014) assumes every concrete provider
# exposes the same five functions plus an inventory metadata block.
# Each function MUST exit non-zero on failure with a clear message
# and MUST NOT echo or log credentials.
#
# Credentials live at ~/<name>.token, mode 0600 (the same convention
# as ~/github.token). Never commit a token, never push a token onto a
# fabric host: tokens stay on the operator's machine.
#
# Inventory metadata
# ------------------
# provider_label : short slug; matches the file name and is recorded
#                  on every host adopted/provisioned through this
#                  plugin.
# default_region : provider-native region/datacenter ID used when the
#                  operator did not pass --region.
# default_size   : provider-native instance type used when the
#                  operator did not pass --size.
# docs_url       : link to the provider's API or product docs.
#
# Function contract
# -----------------
# create_vm   <name> <region> <size> [--ssh-key <path>] ...
#   Provision one VM. Print one JSON object on stdout describing the
#   created instance: {"id":"...","ipv4":"...","region":"...",
#   "size":"...","provider":"<provider_label>"}.
#
# destroy_vm  <id>
#   Delete the VM by provider-native ID. No-op if already gone.
#
# list_vms
#   Print one JSON object per line on stdout, one per VM owned by
#   this token. Same shape as create_vm output.
#
# region_list
#   Print one region slug per line.
#
# size_list   [region]
#   Print one size slug per line. Optional region filter.
#
# Style
# -----
# - bash strict mode (set -euo pipefail).
# - Read the token from ~/<provider_label>.token if GITHUB_TOKEN-style
#   env override is not set. Validate mode 0600 before reading.
# - Use curl with --fail --silent --show-error and explicit
#   --max-time. Never pipe credentials through process arguments
#   (use --header @file or stdin).
# - Caveman style for any user-facing error: "<provider>: <what>
#   <why>".

provider_label=""           # e.g. "contabo"
default_region=""           # e.g. "EU"
default_size=""             # e.g. "VPS-S"
docs_url=""                 # e.g. "https://api.contabo.com/"

create_vm() {
  printf '%s: create_vm not implemented\n' "$provider_label" >&2
  return 1
}

destroy_vm() {
  printf '%s: destroy_vm not implemented\n' "$provider_label" >&2
  return 1
}

list_vms() {
  printf '%s: list_vms not implemented\n' "$provider_label" >&2
  return 1
}

region_list() {
  printf '%s: region_list not implemented\n' "$provider_label" >&2
  return 1
}

size_list() {
  printf '%s: size_list not implemented\n' "$provider_label" >&2
  return 1
}
