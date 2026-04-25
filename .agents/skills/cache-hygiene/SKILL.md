---
name: cache-hygiene
description: Use when changing CI cache configuration, bootstrap fetch helpers, per-tool prune rules, source-mirror behavior, bootstrap-artifact publish/restore, or any code path that decides what gets saved into reusable cache. Encodes the template's "minimal, accelerator-only, refetchable" principles.
---

# cache-hygiene

The template's caches and accelerators (`.local/toolchain`,
`.local/stamps`, source mirrors, bootstrap-artifact releases, GitHub
Actions cache entries) follow a small set of invariants. Violating
any of them either bloats the cache, makes a fresh clone fragile, or
turns CI noisy.

## Principles

### 1. Accelerators, never load-bearing

A miss must not break a fresh clone. Source paths remain canonical.
The cache exists to skip work, not to store anything that cannot be
re-derived.

Applies to: `.local/`, source mirrors, bootstrap-artifact tarballs,
GitHub Actions cache.

### 2. Cache the smallest reusable surface

Cache only what survives between runs and pays its weight on
restore.

- CI restores `.local/toolchain` + `.local/stamps`. Nothing else
  under `.local/` is cached (downloaded source archives,
  intermediate build artifacts, scratch dirs are all excluded).
- Bootstrap-artifact tarballs ship the executed surface only.
- Per-tool fetchers should declare `TOOL_PRUNE_PATHS` to drop
  unused subtrees of large toolchains (compiler man pages, unused
  cross-targets, headers for languages we do not use, etc.).

### 3. Canonical writes only

Saving to GitHub Actions cache happens **only on non-PR runs**
(typically `main`). PR jobs `restore` and never `save`. Two writers
racing for the same immutable cache key produce noisy "another job
may be creating this cache" failures even when both succeed; the
canonical-only pattern eliminates that.

### 4. Cache-key invalidation has one source

`bootstrap/vars/local_cache_key.sh` is the sentinel CI hashes for the
cache key, alongside `.agents/repo.json` and `bootstrap/tools/*.sh`.

- Editing a per-tool spec (`bootstrap/tools/<tool>.sh`) naturally
  bumps the cache key.
- Editing the helpers (`bootstrap/fetch_binary.sh`,
  `bootstrap/fetch_source.sh`) or the prune rules embedded in them
  does **not** change the per-tool files; bump
  `bootstrap/vars/local_cache_key.sh:cache_epoch` to invalidate.
- Editing wrappers, command dispatch, docs, or hooks should not
  cold-start CI; keep them out of the hashed manifest.

### 5. Reuse build outputs across CI stages

Commands that both build and consume build outputs expose
`--no-build` (or equivalent reuse mode). CI runs the explicit build
once per debug/release, then runs reuse-mode test, package, bench,
and system-test steps. Failures identify the broken stage; the build
does not happen four times.

### 6. Refresh paths are explicit

Normal bootstrap is non-fatal on a missing or stale cache. Refresh /
upload / publish commands (`source_mirror upload`, bootstrap-artifact
publish) are the only commands that exit non-zero on missing
configured inputs — those commands exist specifically to maintain
the cache.

### 7. Warm the LRU

GitHub Actions evicts cache entries unused for ~7 days. The
`cache_warm.yml` workflow restores the same keys daily so a quiet
`main` does not lose its toolchain cache. Restore misses are
acceptable and must not fail the workflow.

## Operations

### Adding a tool that bloats the cache

1. Run the fetch once and `du -sh .local/toolchain/$REPO_ARCH/`.
2. Identify subtrees that are not on the executed surface
   (`find` for unreferenced binaries, man pages, unused targets).
3. Set `TOOL_PRUNE_PATHS=(...)` in the per-tool spec.
4. Re-fetch with the stamp removed; confirm size dropped and the
   tool still runs end-to-end.
5. Commit. The CI cache key bumps because `bootstrap/tools/<tool>.sh`
   changed.

### Changing helper behavior (non-tool-specific)

1. Edit `bootstrap/fetch_binary.sh` or `bootstrap/fetch_source.sh`.
2. Bump `bootstrap/vars/local_cache_key.sh:cache_epoch` so existing
   caches are invalidated.
3. Commit both edits in the same change.

### Adding a new path to the CI cache

Don't, unless it is genuinely reused across runs and survives a
fresh clone deterministically. Adding `.local/cache/` (downloaded
source archives) is the classic anti-pattern: archives are big, are
not consulted unless the toolchain itself is rebuilt, and bloat
every restore for no benefit.

### Diagnosing a cache miss that should have hit

1. Confirm the requested key matches the saved key
   (`hashFiles(...)` inputs are stable).
2. Confirm the run is on a path eligible to write
   (non-PR, no canceled prior run).
3. Confirm GitHub LRU has not evicted: check `cache_warm.yml`
   recent runs.
4. If the miss is structural (key changed), proceed — the next
   non-PR run repopulates.

## Read first

- `AGENTS.md` §3 (maintenance contract) and §14 (CI).
- `bootstrap/vars/local_cache_key.sh` for the cache-key sentinel.
- `bootstrap/fetch_binary.sh` / `bootstrap/fetch_source.sh` for
  the prune mechanism.
- `.github/workflows/ci.yml` for the canonical-write pattern.
- `.github/workflows/cache_warm.yml` for the LRU-warm pattern.
