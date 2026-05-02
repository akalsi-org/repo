#!/usr/bin/env bash
# Thin shim so `tools/infra/adopt.sh ...` works alongside
# `./repo.sh infra adopt ...`. The Python dispatcher carries the
# real logic; this script just delegates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export REPO_ROOT

exec python3 "$REPO_ROOT/tools/infra" adopt "$@"
