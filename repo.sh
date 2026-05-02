#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
repo.sh - repository environment launcher

Usage:
  ./repo.sh                  Spawn a shell with repository env vars set.
  ./repo.sh <cmd> [args..]   Run a command with repository env vars set.
  ./repo.sh -h | --help      Show this message.

Exported env:
  REPO_ROOT       worktree root
  REPO_LOCAL      local cache/build state
  REPO_TOOLCHAIN  optional local toolchain directory
  REPO_ARCH       host arch
  REPO_SHELL      set to 1 inside this launcher
EOF
}

case "${1:-}" in
  -h|--help|help) usage; exit 0 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "$SCRIPT_DIR/../.bare" ]]; then
  REPO_LOCAL_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)/.local"
else
  REPO_LOCAL_DEFAULT="$SCRIPT_DIR/.local"
fi

detect_arch() {
  local m
  m="$(uname -m)"
  case "$m" in
    x86_64|amd64) echo "x86_64" ;;
    aarch64|arm64) echo "aarch64" ;;
    *) echo "$m" ;;
  esac
}

export REPO_ROOT="$SCRIPT_DIR"
export REPO_LOCAL="${REPO_LOCAL:-$REPO_LOCAL_DEFAULT}"
export REPO_ARCH="${REPO_ARCH:-$(detect_arch)}"
export REPO_TOOLCHAIN="${REPO_TOOLCHAIN:-$REPO_LOCAL/toolchain/$REPO_ARCH}"
export REPO_SHELL=1
export PYTHON_JIT="${PYTHON_JIT:-1}"

mkdir -p "$REPO_LOCAL/toolchain/$REPO_ARCH" "$REPO_LOCAL/stamps"

query_bootstrap_spec() {
  local spec="$1"
  (
    set -euo pipefail
    BOOTSTRAP_PLAN_ONLY=1
    TOOL_NAME=
    TOOL_DEPS=()
    # shellcheck source=/dev/null
    . "$spec"
    printf '%s\t%s\n' "$TOOL_NAME" "${TOOL_DEPS[*]:-}"
  )
}

bootstrap_status_color_enabled() {
  case "${REPO_BOOTSTRAP_COLOR:-auto}" in
    always) return 0 ;;
    never) return 1 ;;
    auto|"") [[ -t 2 && -z "${NO_COLOR:-}" ]] ;;
    *)
      printf 'repo.sh: error: REPO_BOOTSTRAP_COLOR must be auto, always, or never\n' >&2
      exit 1
      ;;
  esac
}

color_bootstrap_stderr() {
  local green=$'\033[32m'
  local yellow=$'\033[33m'
  local red=$'\033[31m'
  local dim=$'\033[2m'
  local reset=$'\033[0m'
  local line
  local color

  while IFS= read -r line; do
    color="$dim"
    case "$line" in
      *"error:"*|*"failed"*|*"mismatch"*|*"missing"*|*"not found"*) color="$red" ;;
      *"skipping"*|*"not installed"*|*"unavailable"*) color="$yellow" ;;
      *"cached"*|*"installed"*|*"built"*|*"host available"*) color="$green" ;;
    esac
    printf '%s%s%s\n' "$color" "$line" "$reset" >&2
  done
}

source_bootstrap_spec() {
  local spec="$1"

  unset -f tool_post_install 2>/dev/null || true
  if bootstrap_status_color_enabled; then
    # shellcheck source=/dev/null
    . "$spec" 2> >(color_bootstrap_stderr)
  else
    # shellcheck source=/dev/null
    . "$spec"
  fi
}

declare -A bootstrap_spec_by_name=()
declare -A bootstrap_deps_by_name=()
declare -A bootstrap_done_by_name=()
bootstrap_names=()
for spec in "$REPO_ROOT"/bootstrap/tools/*.sh; do
  [[ -e "$spec" ]] || continue
  metadata="$(query_bootstrap_spec "$spec")"
  IFS=$'\t' read -r tool_name tool_deps <<<"$metadata"
  if [[ -z "$tool_name" ]]; then
    printf 'repo.sh: error: bootstrap spec %s did not set TOOL_NAME\n' "$spec" >&2
    exit 1
  fi
  if [[ -n "${bootstrap_spec_by_name[$tool_name]:-}" ]]; then
    printf 'repo.sh: error: duplicate bootstrap TOOL_NAME %s\n' "$tool_name" >&2
    exit 1
  fi
  bootstrap_names+=("$tool_name")
  bootstrap_spec_by_name[$tool_name]="$spec"
  bootstrap_deps_by_name[$tool_name]="$tool_deps"
done

for name in "${bootstrap_names[@]}"; do
  for dep in ${bootstrap_deps_by_name[$name]}; do
    if [[ "$dep" == "$name" ]]; then
      printf 'repo.sh: error: bootstrap tool %s depends on itself\n' "$name" >&2
      exit 1
    fi
    if [[ -z "${bootstrap_spec_by_name[$dep]:-}" ]]; then
      printf 'repo.sh: error: bootstrap tool %s depends on unknown tool %s\n' "$name" "$dep" >&2
      exit 1
    fi
  done
done

bootstrap_ready_batches=()
remaining_count=${#bootstrap_names[@]}
while (( remaining_count > 0 )); do
  ready_names=()
  for name in "${bootstrap_names[@]}"; do
    [[ -z "${bootstrap_done_by_name[$name]:-}" ]] || continue
    ready=1
    for dep in ${bootstrap_deps_by_name[$name]}; do
      if [[ -z "${bootstrap_done_by_name[$dep]:-}" ]]; then
        ready=0
        break
      fi
    done
    (( ready == 1 )) && ready_names+=("$name")
  done
  if (( ${#ready_names[@]} == 0 )); then
    printf 'repo.sh: error: bootstrap dependency cycle among:' >&2
    for name in "${bootstrap_names[@]}"; do
      [[ -n "${bootstrap_done_by_name[$name]:-}" ]] || \
        printf ' %s(deps:%s)' "$name" "${bootstrap_deps_by_name[$name]}" >&2
    done
    printf '\n' >&2
    exit 1
  fi
  bootstrap_ready_batches+=("${ready_names[*]}")
  for name in "${ready_names[@]}"; do
    bootstrap_done_by_name[$name]=1
    remaining_count=$((remaining_count - 1))
  done
done
unset -f tool_post_install 2>/dev/null || true

json_string() {
  local value="$1"
  local escaped=""
  local char
  local i
  for ((i = 0; i < ${#value}; i += 1)); do
    char="${value:i:1}"
    case "$char" in
      \\) escaped+='\\' ;;
      '"') escaped+='\"' ;;
      $'\n') escaped+='\n' ;;
      $'\r') escaped+='\r' ;;
      $'\t') escaped+='\t' ;;
      *) escaped+="$char" ;;
    esac
  done
  printf '"%s"' "$escaped"
}

print_bootstrap_plan_json() {
  local first_tool=1
  local first_dep
  local first_batch=1
  local first_batch_tool
  local name
  local dep
  local batch

  printf '{"tools":['
  for name in "${bootstrap_names[@]}"; do
    (( first_tool == 1 )) || printf ','
    first_tool=0
    printf '{"name":'
    json_string "$name"
    printf ',"deps":['
    first_dep=1
    for dep in ${bootstrap_deps_by_name[$name]}; do
      (( first_dep == 1 )) || printf ','
      first_dep=0
      json_string "$dep"
    done
    printf '],"spec_path":'
    json_string "${bootstrap_spec_by_name[$name]}"
    printf '}'
  done
  printf '],"ready_batches":['
  for batch in "${bootstrap_ready_batches[@]}"; do
    (( first_batch == 1 )) || printf ','
    first_batch=0
    printf '['
    first_batch_tool=1
    for name in $batch; do
      (( first_batch_tool == 1 )) || printf ','
      first_batch_tool=0
      json_string "$name"
    done
    printf ']'
  done
  printf ']}\n'
}

if [[ "${1:-}" == "__repo_bootstrap_plan" ]]; then
  shift
  plan_format=text
  case "${1:-}" in
    "") ;;
    --json) plan_format=json; shift ;;
    *)
      printf 'repo.sh: error: usage: ./repo.sh __repo_bootstrap_plan [--json]\n' >&2
      exit 1
      ;;
  esac
  if [[ $# -ne 0 ]]; then
    printf 'repo.sh: error: usage: ./repo.sh __repo_bootstrap_plan [--json]\n' >&2
    exit 1
  fi
  if [[ "$plan_format" == json ]]; then
    print_bootstrap_plan_json
    exit 0
  fi
  batch_index=0
  for batch in "${bootstrap_ready_batches[@]}"; do
    printf 'batch %d: %s\n' "$batch_index" "$batch"
    (( batch_index += 1 ))
  done
  exit 0
fi

for batch in "${bootstrap_ready_batches[@]}"; do
  for name in $batch; do
    source_bootstrap_spec "${bootstrap_spec_by_name[$name]}"
  done
done
unset -f tool_post_install 2>/dev/null || true

export PATH="$REPO_ROOT/tools:$REPO_ROOT/tools/bin:$REPO_TOOLCHAIN/bin:$REPO_TOOLCHAIN/bwrap/bin:$PATH"

if [[ "${1:-}" == "__repo_pack_bootstrap_artifacts" ]]; then
  shift
  [[ $# -eq 1 ]] || {
    printf 'repo.sh: error: usage: ./repo.sh __repo_pack_bootstrap_artifacts OUT_DIR\n' >&2
    exit 1
  }
  exec python3 "$REPO_ROOT/tools/bootstrap_artifact_release.py" pack \
    --root "$REPO_ROOT" \
    --out-dir "$1"
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

shell="${SHELL:-/bin/sh}"
exec "$shell"
