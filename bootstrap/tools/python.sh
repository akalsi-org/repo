#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=python
TOOL_VERSION=3.14.4-20260414-musl-loader
TOOL_DEPS=(bwrap)

# python-build-standalone musl install_only_stripped builds. Prefer
# Alpine/static product portability over GNU-libc runner convenience.
TOOL_URL_x86_64="https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.14.4%2B20260414-x86_64-unknown-linux-musl-install_only_stripped.tar.gz"
TOOL_SHA256_x86_64=d6005226cd24e780630626232c7a63243d4885fdf975dcf930a0758a0759ce14

TOOL_URL_aarch64="https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.14.4%2B20260414-aarch64-unknown-linux-musl-install_only_stripped.tar.gz"
TOOL_SHA256_aarch64=a10687b226e0941632569836bc1d8fa6353a8e3e8424316467ca9cdf220b983d

TOOL_EXTRACT_PREFIX=python
TOOL_INSTALL_BIN=bin/python3
TOOL_PRUNE_PATHS=(
  share/man
)

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

tool_post_install() {
  local prefix="$1" loader_arch real
  case "$REPO_ARCH" in
    x86_64) loader_arch=x86_64 ;;
    aarch64) loader_arch=aarch64 ;;
    *) printf 'python: unsupported musl loader arch %s\n' "$REPO_ARCH" >&2; return 1 ;;
  esac

  for exe in python3.14 python3; do
    if [[ -L "$prefix/bin/$exe" ]]; then
      continue
    fi
    real="$prefix/bin/$exe.real"
    if [[ ! -e "$real" ]]; then
      mv "$prefix/bin/$exe" "$real"
    fi
    cat >"$prefix/bin/$exe" <<SHIM
#!/bin/sh
set -eu
script_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd -P)
toolchain_dir=\$(dirname -- "\$script_dir")
rootfs="\$toolchain_dir/alpine"
export PYTHON_JIT="\${PYTHON_JIT:-1}"
exec "\$rootfs/lib/ld-musl-${loader_arch}.so.1" \\
  --library-path "\$rootfs/lib:\$rootfs/usr/lib" \\
  "\$script_dir/${exe}.real" "\$@"
SHIM
    chmod +x "$prefix/bin/$exe"
  done
}

. "$REPO_ROOT/bootstrap/fetch_binary.sh"
