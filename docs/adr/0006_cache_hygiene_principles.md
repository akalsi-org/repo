# Cache hygiene principles

The template's caches (`.local/toolchain`, `.local/stamps`, source
mirrors, bootstrap-artifact releases, GitHub Actions cache) are
accelerators only. The principles below are codified in
`.agents/skills/cache-hygiene/SKILL.md` and enforced by convention,
not by automated check:

1. Accelerators, never load-bearing — a miss must not break a fresh
   clone.
2. Cache the smallest reusable surface — `.local/toolchain` +
   `.local/stamps`, with per-tool `TOOL_PRUNE_PATHS` trimming unused
   subtrees of large toolchains.
3. Canonical writes only — non-PR runs save; PR runs only restore.
4. Cache-key invalidation has one source —
   `bootstrap/vars/local_cache_key.sh` plus `.agents/repo.json` plus
   `bootstrap/tools/*.sh`.
5. Reuse build outputs across CI stages — every command that builds
   and consumes outputs offers a `--no-build` reuse mode.
6. Refresh paths are explicit — only upload/publish/refresh commands
   exit non-zero on missing inputs.
7. Warm the LRU — `cache_warm.yml` daily restores; misses are not
   fatal.

These principles came from observed cache-bloat and CI-noise issues
in apf (commits aa6fc1f, 0744bdf, f448b27, 5e3302a, 0cc567f, 369319e)
and have been adapted to the polyglot per-tool fetcher pattern this
template uses.
