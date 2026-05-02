#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=zig
TOOL_VERSION=0.16.0
TOOL_DEPS=()

# Single bundled C/C++ toolchain: clang + LLD + libc + libc++ from the
# upstream Zig release tarball. Default target is musl; that matches the
# pinned musl Python ABI from ADR-0008 and the Alpine/static-portable
# baseline. See ADR-0013 for the full rationale (Zig over GCC, libc++
# over libstdc++).
TOOL_URL_x86_64="https://ziglang.org/download/${TOOL_VERSION}/zig-x86_64-linux-${TOOL_VERSION}.tar.xz"
TOOL_SHA256_x86_64=70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00

TOOL_URL_aarch64="https://ziglang.org/download/${TOOL_VERSION}/zig-aarch64-linux-${TOOL_VERSION}.tar.xz"
TOOL_SHA256_aarch64=ea4b09bfb22ec6f6c6ceac57ab63efb6b46e17ab08d21f69f3a48b38e1534f17

# Tarball prefix is per-arch (zig-<arch>-linux-<ver>/). fetch_binary copies
# the contents of $TOOL_EXTRACT_PREFIX into $REPO_TOOLCHAIN, so the zig
# binary lands at $REPO_TOOLCHAIN/zig and the standard library at
# $REPO_TOOLCHAIN/lib/. tool_post_install symlinks bin/zig for $PATH.
TOOL_EXTRACT_PREFIX="zig-${REPO_ARCH}-linux-${TOOL_VERSION}"
TOOL_INSTALL_BIN=zig

# DO NOT prune lib/. Zig recompiles libc and libc++ from sources under
# lib/ on first use of each target — pruning breaks the toolchain. doc/
# is the only safe prune target.
TOOL_PRUNE_PATHS=(
  doc
)

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

tool_post_install() {
  local prefix="$1"
  mkdir -p "$prefix/bin"
  ln -sfn "../zig" "$prefix/bin/zig"
}

. "$REPO_ROOT/bootstrap/fetch_binary.sh"
