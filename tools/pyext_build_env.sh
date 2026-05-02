#!/usr/bin/env bash

pyext_build_setup_env() {
  local scratch="$1"
  local repo_arch="${REPO_ARCH:-$(uname -m)}"
  local target toolchain zig_bin python_bin python_config
  case "$repo_arch" in
    amd64) repo_arch=x86_64 ;;
    arm64) repo_arch=aarch64 ;;
  esac
  target="${repo_arch}-linux-musl"
  toolchain="${REPO_TOOLCHAIN:-}"

  zig_bin="$(command -v zig || true)"
  if [[ -z "$zig_bin" && -n "$toolchain" && -x "$toolchain/bin/zig" ]]; then
    zig_bin="$toolchain/bin/zig"
  fi

  mkdir -p "$scratch/cc-wrap"
  cat >"$scratch/cc-wrap/zig-cc-filter.sh" <<'WRAPEOF'
#!/usr/bin/env bash
set -euo pipefail
filtered=()
for arg in "$@"; do
  case "$arg" in
    -Wl,--exclude-libs,*) ;;
    -Wl,--exclude-libs|--exclude-libs) ;;
    *) filtered+=("$arg") ;;
  esac
done
exec "$PYEXT_BUILD_ZIG_BIN" cc -target "$PYEXT_BUILD_TARGET" "${filtered[@]}"
WRAPEOF
  cat >"$scratch/cc-wrap/zig-cxx-filter.sh" <<'WRAPEOF'
#!/usr/bin/env bash
set -euo pipefail
filtered=()
for arg in "$@"; do
  case "$arg" in
    -Wl,--exclude-libs,*) ;;
    -Wl,--exclude-libs|--exclude-libs) ;;
    *) filtered+=("$arg") ;;
  esac
done
exec "$PYEXT_BUILD_ZIG_BIN" c++ -target "$PYEXT_BUILD_TARGET" "${filtered[@]}"
WRAPEOF
  chmod +x "$scratch/cc-wrap/zig-cc-filter.sh" "$scratch/cc-wrap/zig-cxx-filter.sh"

  if [[ -z "${CC+x}" ]]; then
    if [[ -z "$zig_bin" ]]; then
      printf 'pyext-build: skip: zig not available; pinned Zig bootstrap is required for musl extension builds\n' >&2
      return 77
    fi
    export PYEXT_BUILD_ZIG_BIN="$zig_bin"
    export PYEXT_BUILD_TARGET="$target"
    export CC="$scratch/cc-wrap/zig-cc-filter.sh"
  fi
  if [[ -z "${CXX+x}" ]]; then
    if [[ -z "$zig_bin" ]]; then
      printf 'pyext-build: skip: zig not available; pinned Zig bootstrap is required for musl extension builds\n' >&2
      return 77
    fi
    export PYEXT_BUILD_ZIG_BIN="$zig_bin"
    export PYEXT_BUILD_TARGET="$target"
    export CXX="$scratch/cc-wrap/zig-cxx-filter.sh"
  fi

  python_bin="${PYTHON:-python3}"
  if [[ -z "${PYTHON+x}" && -n "$toolchain" && -x "$toolchain/bin/python3" ]]; then
    python_bin="$toolchain/bin/python3"
  fi
  python_config="${PYTHON_CONFIG:-python3-config}"
  if [[ -z "${PYTHON_CONFIG+x}" && -n "$toolchain" && -x "$toolchain/bin/python3-config" ]]; then
    python_config="$toolchain/bin/python3-config"
  fi

  mapfile -t py_flags < <("$python_config" --cflags --ldflags --embed)
  cflags="${py_flags[0]:-}"
  ldflags="${py_flags[*]:1}"
  export CFLAGS="${CFLAGS:-} $cflags"
  export LDFLAGS="${LDFLAGS:-} $ldflags"
  export PYTHON="$python_bin"
  export PYTHON_CONFIG="$python_config"
}
