#!/usr/bin/env bash
# bootstrap/fetch_source.sh — fetch a pinned source tarball, build, install
# into $REPO_TOOLCHAIN.
#
# Caller declares:
#
#   TOOL_NAME        required.
#   TOOL_VERSION     required.
#   TOOL_SRC_URL     required, source tarball URL.
#   TOOL_SRC_SHA256  required, SHA256 hex.
#   TOOL_SRC_PREFIX  optional, top-level dir inside the tarball.
#                    Default: derived from URL basename minus extension.
#   TOOL_BUILD_CMDS  required, bash array of commands to run inside the
#                    extracted source dir. Each is `eval`'d, so $REPO_TOOLCHAIN
#                    and other env vars expand naturally.
#   TOOL_INSTALL_BIN optional, path under $REPO_TOOLCHAIN that must end up
#                    executable. Default: bin/$TOOL_NAME.
#   TOOL_PRUNE_PATHS optional, bash array of paths (relative to the install
#                    prefix) to delete after build. Bump
#                    bootstrap/vars/local_cache_key.sh:cache_epoch when prune
#                    rules change.
#
# Source from a per-tool spec:
#
#   . "$REPO_ROOT/bootstrap/fetch_source.sh"

set -euo pipefail

: "${REPO_ROOT:?REPO_ROOT must be set; source this from ./repo.sh}"
: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"
: "${TOOL_NAME:?per-tool spec must set TOOL_NAME}"
: "${TOOL_VERSION:?per-tool spec must set TOOL_VERSION}"
: "${TOOL_SRC_URL:?per-tool spec must set TOOL_SRC_URL}"
: "${TOOL_SRC_SHA256:?per-tool spec must set TOOL_SRC_SHA256}"

if [[ -z "${TOOL_BUILD_CMDS+x}" ]]; then
  printf '%s: TOOL_BUILD_CMDS array is required for source builds\n' \
    "$TOOL_NAME" >&2
  return 1 2>/dev/null || exit 1
fi

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
if [[ -f "$stamp" ]]; then
  printf '%s: cached (%s, %s)\n' "$TOOL_NAME" "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

mkdir -p "$REPO_TOOLCHAIN" "$REPO_LOCAL/stamps"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' RETURN EXIT

archive="$scratch/${TOOL_NAME}.tar.gz"
printf '%s: fetching source %s\n' "$TOOL_NAME" "$TOOL_SRC_URL" >&2
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$archive" "$TOOL_SRC_URL"; then
  printf '%s: source fetch failed (%s)\n' "$TOOL_NAME" "$TOOL_SRC_URL" >&2
  return 1 2>/dev/null || exit 1
fi

actual="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual" != "$TOOL_SRC_SHA256" ]]; then
  printf '%s: source sha256 mismatch (expected %s, got %s)\n' \
    "$TOOL_NAME" "$TOOL_SRC_SHA256" "$actual" >&2
  return 1 2>/dev/null || exit 1
fi

mkdir -p "$scratch/src"
tar -xzf "$archive" -C "$scratch/src"

if [[ -n "${TOOL_SRC_PREFIX:-}" ]]; then
  build_dir="$scratch/src/$TOOL_SRC_PREFIX"
else
  build_dir="$(find "$scratch/src" -mindepth 1 -maxdepth 1 -type d | head -n1)"
fi

if [[ ! -d "$build_dir" ]]; then
  printf '%s: cannot locate extracted source dir\n' "$TOOL_NAME" >&2
  return 1 2>/dev/null || exit 1
fi

(
  cd "$build_dir"
  for cmd in "${TOOL_BUILD_CMDS[@]}"; do
    printf '%s: $ %s\n' "$TOOL_NAME" "$cmd" >&2
    eval "$cmd"
  done
)

if [[ -n "${TOOL_PRUNE_PATHS+x}" ]]; then
  for p in "${TOOL_PRUNE_PATHS[@]}"; do
    [[ -z "$p" ]] && continue
    target="$REPO_TOOLCHAIN/$p"
    if [[ -e "$target" || -L "$target" ]]; then
      printf '%s: pruning %s\n' "$TOOL_NAME" "$p" >&2
      rm -rf "$target"
    fi
  done
fi

install_bin="${TOOL_INSTALL_BIN:-bin/$TOOL_NAME}"
target_bin="$REPO_TOOLCHAIN/$install_bin"
if [[ ! -e "$target_bin" ]]; then
  printf '%s: install bin %s not found after build\n' \
    "$TOOL_NAME" "$target_bin" >&2
  return 1 2>/dev/null || exit 1
fi
chmod +x "$target_bin"

printf '%s\n' "$TOOL_VERSION" > "$stamp"
printf '%s: built (%s, %s)\n' "$TOOL_NAME" "$TOOL_VERSION" "$REPO_ARCH" >&2
