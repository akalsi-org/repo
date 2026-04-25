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
export PATH="$REPO_ROOT/tools:$REPO_ROOT/tools/bin:$PATH"

mkdir -p "$REPO_LOCAL"

if [[ "${1:-}" == "__repo-pack-bootstrap-artifacts" ]]; then
  shift
  [[ $# -eq 1 ]] || {
    printf 'repo.sh: error: usage: ./repo.sh __repo-pack-bootstrap-artifacts OUT_DIR\n' >&2
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
