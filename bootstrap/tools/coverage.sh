#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=coverage
TOOL_VERSION=7.13.0
TOOL_DEPS=(python)
COVERAGE_PY3_NONE_ANY_SHA256=850d2998f380b1e266459ca5b47bc9e7daf9af1d070f66317972f382d46f1904

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
pinned_py="$REPO_TOOLCHAIN/bin/python3"
site_pkgs="$REPO_TOOLCHAIN/lib/python3.14/site-packages"

if [[ -f "$stamp" ]] && "$pinned_py" -c "import coverage" >/dev/null 2>&1; then
  printf 'coverage: cached (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

if [[ ! -x "$pinned_py" ]]; then
  printf 'coverage: pinned python not found at %s\n' "$pinned_py" >&2
  return 1 2>/dev/null || exit 1
fi

mkdir -p "$site_pkgs" "$REPO_TOOLCHAIN/bin" "$REPO_LOCAL/stamps"

req_file="$REPO_LOCAL/coverage-requirements.txt"
cat >"$req_file" <<REQ
coverage==$TOOL_VERSION \\
  --hash=sha256:$COVERAGE_PY3_NONE_ANY_SHA256
REQ

export PYTHONEXECUTABLE="$pinned_py"
if "$pinned_py" -m pip install --require-hashes --only-binary=:all: --target="$site_pkgs" -r "$req_file"; then
  cat >"$REPO_TOOLCHAIN/bin/coverage" <<WRAP
#!/bin/sh
exec env PYTHONPATH="$site_pkgs\${PYTHONPATH:+:\$PYTHONPATH}" "$pinned_py" -m coverage "\$@"
WRAP
  chmod +x "$REPO_TOOLCHAIN/bin/coverage"
  printf '%s\n' "$TOOL_VERSION" >"$stamp"
  printf 'coverage: installed (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
else
  printf 'coverage: install skipped; network or wheel unavailable\n' >&2
fi
