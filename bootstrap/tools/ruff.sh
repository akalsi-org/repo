#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=ruff
TOOL_VERSION=0.14.9
TOOL_DEPS=(python)

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

if command -v ruff >/dev/null 2>&1; then
  printf 'ruff: host available (%s)\n' "$(ruff --version)" >&2
else
  printf 'ruff: not installed; tools/lint falls back to compileall\n' >&2
fi
