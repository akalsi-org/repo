#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=shfmt
TOOL_VERSION=3.12.0

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

if command -v shfmt >/dev/null 2>&1; then
  printf 'shfmt: host available (%s)\n' "$(shfmt --version)" >&2
else
  printf 'shfmt: not installed; tools/lint skips format diff\n' >&2
fi
