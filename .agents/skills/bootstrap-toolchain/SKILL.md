---
name: bootstrap-toolchain
description: Use when adding, upgrading, or removing pinned tools fetched into .local/toolchain/, when changing the fetch helpers, or when adjusting the cache key that gates reusable bootstrap state.
---

# bootstrap-toolchain

The template fetches pinned third-party tools (compilers, language
runtimes, CLI binaries) into `.local/toolchain/$REPO_ARCH/` so every
machine and CI runner has identical bits without sudo or the system
package manager.

## Layout

```
bootstrap/
  fetch_binary.sh          # generic helper: download tarball + verify SHA + extract
  fetch_source.sh          # generic helper: download source + verify SHA + build with declared cmds
  tools/
    <tool>.sh              # one file per pinned tool; sources one helper
  vars/
    local_cache_key.sh     # cache_epoch + bootstrap_artifact_format sentinels
```

`.local/toolchain/$REPO_ARCH/` is the install prefix every tool's
fetcher writes into. `.local/stamps/<tool>_<version>` records that a
tool was successfully installed; the helper skips re-fetch if the
stamp matches the requested version.

## Per-tool spec

Each `bootstrap/tools/<tool>.sh` declares its inputs as shell variables
and sources one of the helpers:

```sh
# bootstrap/tools/<tool>.sh
TOOL_NAME=<tool>
TOOL_VERSION=<x.y.z>
TOOL_DEPS=(other-tool another-tool)          # optional; bootstrap graph edges

# Binary form:
TOOL_URL_x86_64="https://.../<tool>-x86_64.tar.gz"
TOOL_URL_aarch64="https://.../<tool>-aarch64.tar.gz"
TOOL_SHA256_x86_64="<hex>"
TOOL_SHA256_aarch64="<hex>"
TOOL_EXTRACT_PREFIX="<dir-inside-tarball>"   # optional
TOOL_INSTALL_BIN="bin/<tool>"                # path under prefix that must end up executable
TOOL_PRUNE_PATHS=(                            # optional: drop unused subtrees post-install
  "share/man"
  "share/doc"
)
. "$REPO_ROOT/bootstrap/fetch_binary.sh"

# OR source form:
TOOL_SRC_URL="https://.../<tool>-${TOOL_VERSION}.tar.gz"
TOOL_SRC_SHA256="<hex>"
TOOL_BUILD_CMDS=(
  "./configure --prefix=$REPO_TOOLCHAIN"
  "make -j$(nproc)"
  "make install"
)
. "$REPO_ROOT/bootstrap/fetch_source.sh"
```

Specs that need another bootstrapped tool declare it in `TOOL_DEPS`.
`repo.sh` queries every spec with `BOOTSTRAP_PLAN_ONLY=1`, validates
unknown/self/cyclic dependencies, builds dependency-ready batches, and
executes those batches. Each spec must return before sourcing helpers
when `BOOTSTRAP_PLAN_ONLY=1` so graph planning does not fetch tools.

The helpers do not invent flags — they read these declared variables
and act. To support a new tool, add a new `bootstrap/tools/<tool>.sh`
file. No code in helpers changes unless the helper surface itself is
being extended.

## Invariants

- **Pin everything.** Every download has a SHA256. Helpers fail loudly
  on hash mismatch.
- **Deterministic install prefix.** Always `$REPO_TOOLCHAIN`
  (= `.local/toolchain/$REPO_ARCH`). Never `/usr/local`, never `$HOME`.
- **Idempotent.** A second run that finds a matching stamp file
  short-circuits and prints `<tool>: cached`.
- **Cache-miss is non-fatal during normal bootstrap.** Network
  unreachable → fetch fails clearly, but the bootstrap step reports
  the missing tool and continues so unrelated tooling still works.
  Explicit `bootstrap/refresh` or upload commands may exit non-zero
  on missing inputs because they are explicitly maintaining the cache.
- **Cache-key invalidation.** CI hashes
  `bootstrap/vars/local_cache_key.sh` + `.agents/repo.json` +
  `bootstrap/tools/*.sh`. Editing a tool spec naturally bumps the
  cache key. Helpers themselves are not in the hash — change them
  by bumping `cache_epoch` in `local_cache_key.sh`.

## Cache footprint

Toolchains are often dominated by payload that is never executed
(man pages, unused cross-targets, alternate frontends, header sets
for languages this product does not use). After fetching a tool,
measure its size and prune unused subtrees via `TOOL_PRUNE_PATHS`
in the per-tool spec. See `cache-hygiene/SKILL.md` for the full set
of invariants and the diagnosis playbook.

The prune step runs after extract/build, before the install-bin
existence check. Prune rules are part of the per-tool spec, so
editing them naturally bumps the CI cache key. Editing the helper
itself does not — bump `bootstrap/vars/local_cache_key.sh:cache_epoch`
in the same commit.

## Adding a tool

1. Pick a binary distribution if one exists; otherwise source.
2. Verify the SHA256 yourself (`curl -fsSL <url> | sha256sum`).
3. Write `bootstrap/tools/<tool>.sh` using the spec above.
4. Declare `TOOL_DEPS=(...)` if this tool needs another bootstrap
   spec to run first.
5. Run `./repo.sh __repo_bootstrap_plan` to confirm the dependency
   batch shape.
6. Run `./repo.sh true` to fetch.
7. Confirm `$REPO_TOOLCHAIN/bin/<tool>` is on `PATH`.
8. Commit; CI cache key auto-bumps.

## Upgrading a tool

1. Edit `TOOL_VERSION` and SHAs in the per-tool file.
2. Delete the old stamp: `rm .local/stamps/<tool>_*`.
3. Re-bootstrap.
4. Commit.

## Removing a tool

`git rm bootstrap/tools/<tool>.sh`. The next bootstrap will not
re-install it. `.local/toolchain/` retains the old binary until
manually cleaned; that's harmless because nothing references it.

## Read first

- `bootstrap/fetch_binary.sh` and `bootstrap/fetch_source.sh` for the
  exact variables each helper reads.
- `bootstrap/vars/local_cache_key.sh` for cache invalidation rules.
- `AGENTS.md` Integrations for any tool that needs credentials.
