#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME=mypyc
# Pinned at 1.18.2: latest mypy version whose dep closure is fully
# pure-Python. mypy 1.19+ adds `librt` (a CPython-only native package)
# whose musllinux wheels won't resolve here because pip's musllinux tag
# detection fails when /lib/ld-musl-x86_64.so.1 is absent on the host
# (we use python-build-standalone's loader-shim wrapper instead). Bump
# this to 1.20+ once a `_manylinux.py` shim or bwrap-wrapped install
# lands. See issue (TBD: fast-python: musllinux tag detection).
TOOL_VERSION=1.18.2
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
mkdir -p "$venv"

# Use the pinned standalone musl Python explicitly. The python-build-standalone
# install uses a loader-shim wrapper that resolves a `.real` binary in its
# own bin/ — `python -m venv` would copy the wrapper into the venv but not
# the `.real` sibling, breaking the venv. Side-step venv entirely: pip
# install with `--prefix` produces a self-contained tree where bin/ scripts
# get shebangs that point back at the pinned wrapper (which can find `.real`).
pinned_py="$REPO_TOOLCHAIN/bin/python3"
if [[ ! -x "$pinned_py" ]]; then
  printf 'mypyc: pinned python not found at %s\n' "$pinned_py" >&2
  return 1 2>/dev/null || exit 1
fi

cat >"$req" <<'REQ'
--only-binary=:all:

mypy[mypyc]==1.18.2 \
    --hash=sha256:22a1748707dd62b58d2ae53562ffc4d7f8bcc727e8ac7cbc69c053ddc874d47e
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
if ! "$pinned_py" -m pip install --require-hashes --prefix="$venv" -r "$req"; then
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
site_pkgs="$venv/lib/python3.14/site-packages"
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

printf '%s\n' "$TOOL_VERSION" >"$stamp"
printf 'mypyc: installed (%s, %s)\n' "$TOOL_VERSION" "$REPO_ARCH" >&2
