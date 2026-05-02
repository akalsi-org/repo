#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=shellcheck
TOOL_VERSION=0.11.0

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

if command -v shellcheck >/dev/null 2>&1; then
  printf 'shellcheck: host available (%s)\n' "$(shellcheck --version | sed -n '2p')" >&2
else
  printf 'shellcheck: not installed; tools/lint falls back to bash -n\n' >&2
fi
