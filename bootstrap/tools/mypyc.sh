#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=mypyc
TOOL_VERSION=1.20.2
TOOL_DEPS=(python zig)

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
venv="$REPO_TOOLCHAIN/mypyc"
req="$venv/requirements.txt"

if [[ -f "$stamp" && -x "$venv/bin/mypyc" ]]; then
  printf 'mypyc: cached (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

mkdir -p "$REPO_LOCAL/stamps" "$REPO_TOOLCHAIN"

if [[ ! -x "$REPO_TOOLCHAIN/bin/zig" ]] && ! command -v zig >/dev/null 2>&1; then
  printf 'mypyc: skipping install until zig is available\n' >&2
  return 0 2>/dev/null || exit 0
fi

rm -rf "$venv"
python3 -m venv "$venv"

cat >"$req" <<'REQ'
--only-binary=:all:

mypy[mypyc]==1.20.2 \
    --hash=sha256:a94c5a76ab46c5e6257c7972b6c8cff0574201ca7dc05647e33e795d78680563
mypy_extensions==1.1.0 \
    --hash=sha256:1be4cccdb0f2482337c4743e60421de3a356cd97508abadd57d47403e94f5505
pathspec==1.0.4 \
    --hash=sha256:fb6ae2fd4e7c921a165808a552060e722767cfa526f99ca5156ed2ce45a5c723
setuptools==82.0.1 \
    --hash=sha256:a59e362652f08dcd477c78bb6e7bd9d80a7995bc73ce773050228a348ce2e5bb
typing_extensions==4.15.0 \
    --hash=sha256:f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548
wheel==0.46.3 \
    --hash=sha256:4b399d56c9d9338230118d705d9737a2a4fc7815d8bc4d
REQ

if ! "$venv/bin/python" -m pip install --require-hashes -r "$req"; then
  printf 'mypyc: pinned wheel install failed; leaving tool uninstalled\n' >&2
  rm -rf "$venv"
  return 0 2>/dev/null || exit 0
fi

if [[ ! -x "$venv/bin/mypyc" ]]; then
  printf 'mypyc: install completed but %s missing\n' "$venv/bin/mypyc" >&2
  rm -rf "$venv"
  return 1 2>/dev/null || exit 1
fi

printf '%s\n' "$TOOL_VERSION" >"$stamp"
printf 'mypyc: installed (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
