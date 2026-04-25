# AGENTS.md

## 2.1 Agent Skills

| Skill | Engage when | Definition |
|-------|-------------|------------|

Routes, when present, live in `.agents/skills/index.md`.

## 3. Maintenance Contract

Agents working in this repository must preserve the template as a reusable
bootstrap substrate. Keep repository-specific behavior configured through
`.agents/repo.json`, update `AGENTS.md` when commands, agent assets, hooks, or
subsystem descriptor rules change, and run `./repo.sh agent-check --stale-only`
plus `git diff --check` before handing work back.

Cache and mirror paths are accelerators only. A miss from `.local/`, source
mirror, or bootstrap artifact reuse must not be fatal during normal bootstrap;
the source path remains canonical. Upload/publish commands may fail on missing
or invalid configured inputs because those commands are explicitly maintaining
the cache.

Commands that can perform an expensive build or bootstrap step should expose a
`--no-build` or equivalent reuse flag when they are also useful after an
explicit prior build. CI should prefer the explicit build step followed by
reuse-mode test, package, benchmark, or system-test steps so failures identify
the stage that broke and wrappers do not rebuild the same output repeatedly.

## 5. Repo Layout

- `repo.sh` is the environment launcher.
- `.agents/repo.json` is the repository contract consumed by tools.
- `bootstrap/vars/local-cache-key.sh` invalidates reusable CI `.local/` caches.
- `.agents/skills/`, `.agents/reviews/`, and `.agents/kb-src/` hold agent assets.
- `tools/` holds commands exposed through `repo.sh`.
- `tools/git-hooks/pre-commit` is the managed pre-commit hook source.

## 8. Commands

| Command | Mode | Purpose |
|---------|------|---------|
| `agent` | Python | Query and maintain the repository agent knowledge base. |
| `agent-check` | Python | Check skill routing, docs references, and configured command inventory. |
| `setup` | Python | Install or report local managed repository hooks. |
| `source-mirror` | Python | List or upload configured byte-identical upstream source mirrors. |

## 14. CI

CI restores `.local/` with `actions/cache/restore`, runs the bootstrap and
agent checks through `./repo.sh`, and saves `.local/` only from non-PR runs on
cache misses. Cache keys are scoped by architecture and by
`bootstrap/vars/local-cache-key.sh` plus `.agents/repo.json`.

`cache-warm.yml` periodically restores the same cache keys to reset GitHub's
LRU timer. Restore misses are acceptable and must not fail the workflow.

## 15. Subsystems

| Subsystem | Layer | Purpose | Detail |
|-----------|-------|---------|--------|
