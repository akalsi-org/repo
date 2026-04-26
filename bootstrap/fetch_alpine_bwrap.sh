#!/usr/bin/env bash
# bootstrap/fetch_alpine_bwrap.sh — install Alpine minirootfs + bwrap shim.
#
# Caller declares:
#
#   TOOL_NAME                 required, normally bwrap.
#   TOOL_VERSION              required, bwrap apk version.
#   TOOL_ALPINE_VERSION       required, Alpine minirootfs version.
#   TOOL_ALPINE_BRANCH        required, Alpine branch, e.g. v3.20.
#   TOOL_LIBCAP_VERSION       required, libcap2 apk version.
#   TOOL_ALPINE_SHA256_<arch> required, SHA256 for minirootfs tarball.
#   TOOL_BWRAP_SHA256_<arch>  required, SHA256 for bubblewrap apk.
#   TOOL_LIBCAP_SHA256_<arch> required, SHA256 for libcap2 apk.
#
# The installed layout mirrors the apf sibling repo:
#
#   $REPO_TOOLCHAIN/alpine/        Alpine rootfs with usr/bin/bwrap + libcap.
#   $REPO_TOOLCHAIN/bwrap/bin/bwrap shell shim invoking bwrap via musl loader.

set -euo pipefail

: "${REPO_ROOT:?REPO_ROOT must be set; source this from ./repo.sh}"
: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"
: "${TOOL_NAME:?per-tool spec must set TOOL_NAME}"
: "${TOOL_VERSION:?per-tool spec must set TOOL_VERSION}"
: "${TOOL_ALPINE_VERSION:?per-tool spec must set TOOL_ALPINE_VERSION}"
: "${TOOL_ALPINE_BRANCH:?per-tool spec must set TOOL_ALPINE_BRANCH}"
: "${TOOL_LIBCAP_VERSION:?per-tool spec must set TOOL_LIBCAP_VERSION}"

alpine_sha_var="TOOL_ALPINE_SHA256_${REPO_ARCH}"
bwrap_sha_var="TOOL_BWRAP_SHA256_${REPO_ARCH}"
libcap_sha_var="TOOL_LIBCAP_SHA256_${REPO_ARCH}"
alpine_sha="${!alpine_sha_var:-}"
bwrap_sha="${!bwrap_sha_var:-}"
libcap_sha="${!libcap_sha_var:-}"
if [[ -z "$alpine_sha" || -z "$bwrap_sha" || -z "$libcap_sha" ]]; then
  printf '%s: no bwrap pin for arch %s — skipping\n' "$TOOL_NAME" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${TOOL_LIBCAP_VERSION}_${TOOL_ALPINE_VERSION}_${REPO_ARCH}"
if [[ -f "$stamp" \
      && -x "$REPO_TOOLCHAIN/bwrap/bin/bwrap" \
      && -x "$REPO_TOOLCHAIN/alpine/usr/bin/bwrap" \
      && -e "$REPO_TOOLCHAIN/alpine/usr/lib/libcap.so.2" \
      && -e "$REPO_TOOLCHAIN/alpine/lib/ld-musl-${REPO_ARCH}.so.1" ]]; then
  printf '%s: cached (%s, alpine %s, %s)\n' \
    "$TOOL_NAME" "$TOOL_VERSION" "$TOOL_ALPINE_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

case "$REPO_ARCH" in
  x86_64) loader_arch=x86_64 ;;
  aarch64) loader_arch=aarch64 ;;
  *)
    printf '%s: unsupported bwrap arch %s — skipping\n' "$TOOL_NAME" "$REPO_ARCH" >&2
    return 0 2>/dev/null || exit 0
    ;;
esac

alpine_base="https://dl-cdn.alpinelinux.org/alpine/${TOOL_ALPINE_BRANCH}"
alpine_url="${alpine_base}/releases/${REPO_ARCH}/alpine-minirootfs-${TOOL_ALPINE_VERSION}-${REPO_ARCH}.tar.gz"
bwrap_url="${alpine_base}/main/${REPO_ARCH}/bubblewrap-${TOOL_VERSION}.apk"
libcap_url="${alpine_base}/main/${REPO_ARCH}/libcap2-${TOOL_LIBCAP_VERSION}.apk"

mkdir -p "$REPO_LOCAL/stamps" "$REPO_TOOLCHAIN"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' RETURN EXIT

fetch_verify() {
  local url="$1" sha="$2" out="$3" actual
  printf '%s: fetching %s\n' "$TOOL_NAME" "$url" >&2
  if ! curl -fsSL --retry 3 --retry-delay 2 -o "$out" "$url"; then
    printf '%s: fetch failed (%s)\n' "$TOOL_NAME" "$url" >&2
    return 1
  fi
  actual="$(sha256sum "$out" | awk '{print $1}')"
  if [[ "$actual" != "$sha" ]]; then
    printf '%s: sha256 mismatch for %s (expected %s, got %s)\n' \
      "$TOOL_NAME" "$url" "$sha" "$actual" >&2
    return 1
  fi
}

alpine_tgz="$scratch/alpine.tar.gz"
bwrap_apk="$scratch/bwrap.apk"
libcap_apk="$scratch/libcap.apk"
fetch_verify "$alpine_url" "$alpine_sha" "$alpine_tgz"
fetch_verify "$bwrap_url" "$bwrap_sha" "$bwrap_apk"
fetch_verify "$libcap_url" "$libcap_sha" "$libcap_apk"

rootfs_tmp="$scratch/alpine"
rootfs="$REPO_TOOLCHAIN/alpine"
bwrap_tmp="$scratch/bwrap"
bwrap_dir="$REPO_TOOLCHAIN/bwrap"
mkdir -p "$rootfs_tmp" "$bwrap_tmp/bin"

tar -xzf "$alpine_tgz" -C "$rootfs_tmp"
tar -xzf "$bwrap_apk" -C "$rootfs_tmp" usr/bin/bwrap 2>/dev/null
tar -xzf "$libcap_apk" -C "$rootfs_tmp" \
  usr/lib/libcap.so.2 "usr/lib/libcap.so.${TOOL_LIBCAP_VERSION%-r*}" 2>/dev/null

if [[ ! -x "$rootfs_tmp/usr/bin/bwrap" ]]; then
  printf '%s: bwrap missing after apk extract\n' "$TOOL_NAME" >&2
  return 1 2>/dev/null || exit 1
fi
if [[ ! -e "$rootfs_tmp/usr/lib/libcap.so.2" ]]; then
  printf '%s: libcap.so.2 missing after apk extract\n' "$TOOL_NAME" >&2
  return 1 2>/dev/null || exit 1
fi

cat >"$bwrap_tmp/bin/bwrap" <<SHIM
#!/bin/sh
set -eu
script_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd -P)
bwrap_dir=\$(dirname -- "\$script_dir")
toolchain_dir=\$(dirname -- "\$bwrap_dir")
rootfs="\$toolchain_dir/alpine"
exec "\$rootfs/lib/ld-musl-${loader_arch}.so.1" \\
  --library-path "\$rootfs/lib:\$rootfs/usr/lib" \\
  "\$rootfs/usr/bin/bwrap" "\$@"
SHIM
chmod +x "$bwrap_tmp/bin/bwrap"

rm -rf "$rootfs" "$bwrap_dir"
mv "$rootfs_tmp" "$rootfs"
mv "$bwrap_tmp" "$bwrap_dir"

"$bwrap_dir/bin/bwrap" --version >/dev/null
printf '%s\n' "$TOOL_VERSION" > "$stamp"
printf '%s: installed (%s, alpine %s, %s)\n' \
  "$TOOL_NAME" "$TOOL_VERSION" "$TOOL_ALPINE_VERSION" "$REPO_ARCH" >&2
