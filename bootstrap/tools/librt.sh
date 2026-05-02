#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=librt
TOOL_VERSION=0.9.0
TOOL_DEPS=(python zig)

TOOL_SRC_URL="https://files.pythonhosted.org/packages/source/l/librt/librt-${TOOL_VERSION}.tar.gz"
TOOL_SRC_SHA256=a0951822531e7aee6e0dfb556b30d5ee36bbe234faf60c20a16c01be3530869d

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

: "${REPO_ROOT:?REPO_ROOT must be set; source this from ./repo.sh}"
: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
pinned_py="$REPO_TOOLCHAIN/bin/python3"
site_pkgs="$REPO_TOOLCHAIN/mypyc/lib/python3.14/site-packages"
python_site="$REPO_TOOLCHAIN/lib/python3.14/site-packages"
pth_file="$python_site/librt-mypyc.pth"

verify_import() {
  PYTHONEXECUTABLE="$pinned_py" \
    "$pinned_py" -c "import librt; print(librt.__version__)"
}

if [[ -f "$stamp" ]] && verify_import >/dev/null 2>&1; then
  printf 'librt: cached (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

if [[ ! -x "$pinned_py" ]]; then
  printf 'librt: pinned python not found at %s\n' "$pinned_py" >&2
  return 1 2>/dev/null || exit 1
fi

if [[ ! -x "$REPO_TOOLCHAIN/bin/zig" ]] && ! command -v zig >/dev/null 2>&1; then
  printf 'librt: skipping install until zig is available\n' >&2
  return 0 2>/dev/null || exit 0
fi

mkdir -p "$REPO_LOCAL/stamps" "$site_pkgs" "$python_site"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/librt.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

archive="$scratch/librt-${TOOL_VERSION}.tar.gz"
printf 'librt: fetching source %s\n' "$TOOL_SRC_URL" >&2
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$archive" "$TOOL_SRC_URL"; then
  printf 'librt: source fetch failed (%s)\n' "$TOOL_SRC_URL" >&2
  return 1 2>/dev/null || exit 1
fi

actual="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual" != "$TOOL_SRC_SHA256" ]]; then
  printf 'librt: source sha256 mismatch (expected %s, got %s)\n' \
    "$TOOL_SRC_SHA256" "$actual" >&2
  return 1 2>/dev/null || exit 1
fi

mkdir -p "$scratch/src" "$scratch/wheel"
tar -xzf "$archive" -C "$scratch/src"
build_dir="$(find "$scratch/src" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [[ ! -d "$build_dir" ]]; then
  printf 'librt: cannot locate extracted source dir\n' >&2
  return 1 2>/dev/null || exit 1
fi

. "$REPO_ROOT/tools/pyext_build_env.sh"
PYTHON="$pinned_py"
PYTHON_CONFIG="$REPO_TOOLCHAIN/bin/python3-config"
export PYTHONEXECUTABLE="$pinned_py"
pyext_build_setup_env "$scratch"

build_deps="$scratch/build-deps"
build_req="$scratch/build-requirements.txt"
old_pythonpath="${PYTHONPATH-}"
had_pythonpath=0
if [[ -n "${PYTHONPATH+x}" ]]; then
  had_pythonpath=1
fi
cat >"$build_req" <<'REQ'
--only-binary=:all:

setuptools==82.0.1 \
    --hash=sha256:a59e362652f08dcd477c78bb6e7bd9d80a7995bc73ce773050228a348ce2e5bb
wheel==0.46.3 \
    --hash=sha256:4b399d56c9d9338230118d705d9737a2a468ccca63d5e813e2a4fc7815d8bc4d
REQ
"$pinned_py" -m pip install \
  --require-hashes \
  --no-deps \
  --target="$build_deps" \
  -r "$build_req"

export PYTHONPATH="$build_deps${PYTHONPATH:+:$PYTHONPATH}"

printf 'librt: building wheel with zig cc (%s-linux-musl)\n' "$REPO_ARCH" >&2
if ! "$pinned_py" -m pip wheel \
    --no-deps \
    --no-build-isolation \
    --no-binary=:all: \
    --wheel-dir "$scratch/wheel" \
    "$build_dir"; then
  printf 'librt: source build failed\n' >&2
  return 1 2>/dev/null || exit 1
fi

wheel="$(find "$scratch/wheel" -maxdepth 1 -type f -name "librt-${TOOL_VERSION}-*.whl" | head -n1)"
if [[ -z "$wheel" ]]; then
  printf 'librt: wheel build completed without producing librt wheel\n' >&2
  return 1 2>/dev/null || exit 1
fi

rm -rf "$site_pkgs/librt" "$site_pkgs"/librt-*.dist-info
"$pinned_py" -m pip install --no-deps --target="$site_pkgs" "$wheel"

if (( had_pythonpath == 1 )); then
  export PYTHONPATH="$old_pythonpath"
else
  unset PYTHONPATH
fi

mkdir -p "$site_pkgs/librt"
if [[ ! -f "$site_pkgs/librt/__init__.py" ]]; then
  printf '__version__ = "%s"\n' "$TOOL_VERSION" >"$site_pkgs/librt/__init__.py"
elif ! grep -q '__version__' "$site_pkgs/librt/__init__.py"; then
  printf '\n__version__ = "%s"\n' "$TOOL_VERSION" >>"$site_pkgs/librt/__init__.py"
fi
printf '%s\n' "$site_pkgs" >"$pth_file"

installed_version="$(verify_import)"
if [[ "$installed_version" != "$TOOL_VERSION" ]]; then
  printf 'librt: import verification failed (expected %s, got %s)\n' \
    "$TOOL_VERSION" "$installed_version" >&2
  return 1 2>/dev/null || exit 1
fi

printf '%s\n' "$TOOL_VERSION" >"$stamp"
printf 'librt: installed (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
