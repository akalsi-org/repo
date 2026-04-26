#!/usr/bin/env bash
# bootstrap/fetch_binary.sh — fetch a pinned binary tarball into $REPO_TOOLCHAIN.
#
# Caller declares (all paths absolute or under $REPO_ROOT):
#
#   TOOL_NAME          required, short tool name (used for stamps).
#   TOOL_VERSION       required, x.y.z form.
#   TOOL_URL_<arch>    required, one per supported arch (x86_64, aarch64, ...).
#   TOOL_SHA256_<arch> required, SHA256 hex of the URL's content.
#   TOOL_EXTRACT_PREFIX optional, dir inside tarball that becomes the prefix.
#                       Default: tarball is extracted directly into $REPO_TOOLCHAIN.
#   TOOL_INSTALL_BIN   optional, path under prefix that must end up executable.
#                       Default: bin/$TOOL_NAME.
#   TOOL_PRUNE_PATHS   optional, bash array of paths (relative to the install
#                       prefix) to delete after install. Use to drop unused
#                       subtrees of large toolchains (e.g. LLVM man pages,
#                       unused targets) so the cache stays minimal. Bump
#                       bootstrap/vars/local_cache_key.sh:cache_epoch when
#                       prune rules change.
#
# Source from a per-tool spec:
#
#   . "$REPO_ROOT/bootstrap/fetch_binary.sh"
#
# Idempotent: if .local/stamps/<tool>_<version> exists with matching arch the
# fetch is skipped. Cache miss is non-fatal: a network failure prints a
# diagnostic and exits with the helper's status; the caller (./repo.sh true)
# decides whether to abort.

set -euo pipefail

: "${REPO_ROOT:?REPO_ROOT must be set; source this from ./repo.sh}"
: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"
: "${TOOL_NAME:?per-tool spec must set TOOL_NAME}"
: "${TOOL_VERSION:?per-tool spec must set TOOL_VERSION}"

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
if [[ -f "$stamp" ]]; then
  printf '%s: cached (%s, %s)\n' "$TOOL_NAME" "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

url_var="TOOL_URL_${REPO_ARCH}"
sha_var="TOOL_SHA256_${REPO_ARCH}"
url="${!url_var:-}"
sha="${!sha_var:-}"
if [[ -z "$url" || -z "$sha" ]]; then
  printf '%s: no binary pin for arch %s — skipping\n' "$TOOL_NAME" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

prefix="$REPO_TOOLCHAIN"
install_bin="${TOOL_INSTALL_BIN:-bin/$TOOL_NAME}"

mkdir -p "$prefix" "$REPO_LOCAL/stamps"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' RETURN EXIT

archive="$scratch/${TOOL_NAME}.tar"
case "$url" in
  *.tar.gz|*.tgz)  ext="tar.gz"  ;;
  *.tar.xz)        ext="tar.xz"  ;;
  *.tar.bz2)       ext="tar.bz2" ;;
  *.zip)           ext="zip"     ;;
  *)               ext="tar.gz"  ;;
esac
archive="$scratch/${TOOL_NAME}.${ext}"

printf '%s: fetching %s\n' "$TOOL_NAME" "$url" >&2
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$archive" "$url"; then
  printf '%s: fetch failed (%s)\n' "$TOOL_NAME" "$url" >&2
  return 1 2>/dev/null || exit 1
fi

actual="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual" != "$sha" ]]; then
  printf '%s: sha256 mismatch (expected %s, got %s)\n' \
    "$TOOL_NAME" "$sha" "$actual" >&2
  return 1 2>/dev/null || exit 1
fi

extract_dir="$scratch/extracted"
mkdir -p "$extract_dir"
case "$ext" in
  tar.gz|tgz)  tar -xzf "$archive" -C "$extract_dir" ;;
  tar.xz)      tar -xJf "$archive" -C "$extract_dir" ;;
  tar.bz2)     tar -xjf "$archive" -C "$extract_dir" ;;
  zip)         unzip -q "$archive" -d "$extract_dir" ;;
esac

src="$extract_dir"
if [[ -n "${TOOL_EXTRACT_PREFIX:-}" ]]; then
  src="$extract_dir/$TOOL_EXTRACT_PREFIX"
fi

cp -a "$src/." "$prefix/"

if [[ -n "${TOOL_PRUNE_PATHS+x}" ]]; then
  for p in "${TOOL_PRUNE_PATHS[@]}"; do
    [[ -z "$p" ]] && continue
    target="$prefix/$p"
    if [[ -e "$target" || -L "$target" ]]; then
      printf '%s: pruning %s\n' "$TOOL_NAME" "$p" >&2
      rm -rf "$target"
    fi
  done
fi

target_bin="$prefix/$install_bin"
if [[ ! -e "$target_bin" ]]; then
  printf '%s: install bin %s not found after extract\n' \
    "$TOOL_NAME" "$target_bin" >&2
  return 1 2>/dev/null || exit 1
fi
chmod +x "$target_bin"

if declare -F tool_post_install >/dev/null; then
  tool_post_install "$prefix"
fi

printf '%s\n' "$TOOL_VERSION" > "$stamp"
printf '%s: installed (%s, %s)\n' "$TOOL_NAME" "$TOOL_VERSION" "$REPO_ARCH" >&2
