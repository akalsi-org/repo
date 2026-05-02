#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=mypyc
# mypy 1.20+ supported via librt source-build (#15).
TOOL_VERSION=1.20.1
TOOL_DEPS=(python zig librt)

if [[ "${BOOTSTRAP_PLAN_ONLY:-0}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

: "${REPO_LOCAL:?REPO_LOCAL must be set; source this from ./repo.sh}"
: "${REPO_TOOLCHAIN:?REPO_TOOLCHAIN must be set; source this from ./repo.sh}"
: "${REPO_ARCH:?REPO_ARCH must be set; source this from ./repo.sh}"

stamp="$REPO_LOCAL/stamps/${TOOL_NAME}_${TOOL_VERSION}_${REPO_ARCH}"
venv="$REPO_TOOLCHAIN/mypyc"
req="$venv/requirements.txt"
site_pkgs="$venv/lib/python3.14/site-packages"
pinned_py="$REPO_TOOLCHAIN/bin/python3"

verify_cached_install() {
  [[ -x "$venv/bin/mypyc" ]] || return 1
  PYTHONPATH="$site_pkgs${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONEXECUTABLE="$pinned_py" \
    "$pinned_py" -c "import librt, mypy, setuptools, wheel" >/dev/null 2>&1
  "$venv/bin/mypyc" --version >/dev/null 2>&1
}

if [[ -f "$stamp" ]] && verify_cached_install; then
  printf 'mypyc: cached (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
  return 0 2>/dev/null || exit 0
fi

mkdir -p "$REPO_LOCAL/stamps" "$REPO_TOOLCHAIN"

if [[ ! -x "$REPO_TOOLCHAIN/bin/zig" ]] && ! command -v zig >/dev/null 2>&1; then
  printf 'mypyc: skipping install until zig is available\n' >&2
  return 0 2>/dev/null || exit 0
fi

preserve="$(mktemp -d "${TMPDIR:-/tmp}/mypyc-preserve.XXXXXX")"
if [[ -d "$site_pkgs/librt" ]]; then
  cp -a "$site_pkgs/librt" "$preserve/"
fi
for dist_info in "$site_pkgs"/librt-*.dist-info; do
  [[ -e "$dist_info" ]] || continue
  cp -a "$dist_info" "$preserve/"
done
rm -rf "$venv"
mkdir -p "$venv"
mkdir -p "$site_pkgs"
if compgen -G "$preserve/*" >/dev/null; then
  cp -a "$preserve"/. "$site_pkgs/"
fi
rm -rf "$preserve"

# Use the pinned standalone musl Python explicitly. The python-build-standalone
# install uses a loader-shim wrapper that resolves a `.real` binary in its
# own bin/ — `python -m venv` would copy the wrapper into the venv but not
# the `.real` sibling, breaking the venv. Side-step venv entirely: pip
# install with `--prefix` produces a self-contained tree where bin/ scripts
# get shebangs that point back at the pinned wrapper (which can find `.real`).
if [[ ! -x "$pinned_py" ]]; then
  printf 'mypyc: pinned python not found at %s\n' "$pinned_py" >&2
  return 1 2>/dev/null || exit 1
fi

cat >"$req" <<'REQ'
--only-binary=:all:

mypy[mypyc]==1.20.1 \
    --hash=sha256:1aae28507f253fe82d883790d1c0a0d35798a810117c88184097fe8881052f06
mypy_extensions==1.1.0 \
    --hash=sha256:1be4cccdb0f2482337c4743e60421de3a356cd97508abadd57d47403e94f5505
pathspec==1.0.4 \
    --hash=sha256:fb6ae2fd4e7c921a165808a552060e722767cfa526f99ca5156ed2ce45a5c723
setuptools==82.0.1 \
    --hash=sha256:a59e362652f08dcd477c78bb6e7bd9d80a7995bc73ce773050228a348ce2e5bb
typing_extensions==4.15.0 \
    --hash=sha256:f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548
wheel==0.46.3 \
    --hash=sha256:4b399d56c9d9338230118d705d9737a2a468ccca63d5e813e2a4fc7815d8bc4d
packaging==26.2 \
    --hash=sha256:5fc45236b9446107ff2415ce77c807cee2862cb6fac22b8a73826d0693b0980e
REQ

# PYTHONEXECUTABLE makes pip's subprocess.Popen([sys.executable, ...]) invoke
# the loader-shim wrapper instead of the .real ELF (whose hard-coded musl
# PT_INTERP is /lib/ld-musl-x86_64.so.1, absent on glibc hosts). Without it,
# pip's setuptools/wheel-build subprocesses die at execve.
export PYTHONEXECUTABLE="$pinned_py"
if ! "$pinned_py" -m pip install --require-hashes --no-deps --prefix="$venv" -r "$req"; then
  printf 'mypyc: pinned wheel install failed; leaving tool uninstalled\n' >&2
  rm -rf "$venv"
  return 0 2>/dev/null || exit 0
fi

if [[ ! -x "$venv/bin/mypyc" ]]; then
  printf 'mypyc: install completed but %s missing\n' "$venv/bin/mypyc" >&2
  rm -rf "$venv"
  return 1 2>/dev/null || exit 1
fi

# pip install --prefix= drops bin scripts whose shebang references the pinned
# python, but does NOT teach them where to find their packages — Python's
# default site-packages search ignores --prefix-installed trees. Replace each
# entry-point script with a shell wrapper that sets PYTHONPATH + PYTHONEXECUTABLE
# so it's self-contained.
for bin_name in mypyc mypy dmypy stubgen stubtest; do
  bin_path="$venv/bin/$bin_name"
  if [[ ! -f "$bin_path" ]]; then
    continue
  fi
  cat >"$bin_path" <<WRAP
#!/bin/sh
exec env \\
  PYTHONPATH="$site_pkgs\${PYTHONPATH:+:\$PYTHONPATH}" \\
  PYTHONEXECUTABLE="$pinned_py" \\
  "$pinned_py" -m $bin_name "\$@"
WRAP
  chmod +x "$bin_path"
done

# Surface entry points on PATH via $REPO_TOOLCHAIN/bin/. repo.sh adds
# $REPO_TOOLCHAIN/bin to PATH, so this lets `./repo.sh mypyc ...` and
# `mypyc` (inside ./repo.sh's subshell) work directly. Same pattern as
# zig.sh's bin/zig symlink.
mkdir -p "$REPO_TOOLCHAIN/bin"
for bin_name in mypyc mypy dmypy stubgen stubtest; do
  if [[ -x "$venv/bin/$bin_name" ]]; then
    ln -sfn "../mypyc/bin/$bin_name" "$REPO_TOOLCHAIN/bin/$bin_name"
  fi
done

printf '%s\n' "$TOOL_VERSION" >"$stamp"
printf 'mypyc: installed (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
