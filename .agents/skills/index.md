# Skill Routing Index

Use the smallest skill set that matches the changed paths. This index
is agent-facing routing metadata; the actual procedures live in each
`.agents/skills/<name>/SKILL.md`.

| Path pattern | Skills | Notes |
|--------------|--------|-------|
| `AGENTS.md`, `README.md`, `CONTEXT.md`, `docs/adr/**`, `.agents/skills/index.md` | `doc-sync` | Run `./repo.sh agent_check --stale-only` and `git diff --check`. Keep skill table in sync with this index. |
| `.agents/kb_src/**` | `knowledge-management`, `doc-sync` | Query before writing. Keep JSONL compact. |
| `.agents/skills/*/SKILL.md`, `.agents/skills/*/**.md` | `doc-sync` | New skill folders must appear in `AGENTS.md` skill table and (optionally) in this index. |
| `repo.sh`, `bootstrap/**` | `bootstrap-toolchain`, `cache-hygiene`, `doc-sync` | Edits to fetch helpers do not bump cache key automatically — bump `bootstrap/vars/local_cache_key.sh:cache_epoch`. |
| `bootstrap/tools/*.sh` | `bootstrap-toolchain`, `cache-hygiene` | Edits naturally bump CI cache key via hashFiles. Declare `TOOL_PRUNE_PATHS` for bloated toolchains. |
| `bootstrap/vars/local_cache_key.sh`, `.github/workflows/ci.yml`, `.github/workflows/cache_warm.yml`, `tools/source_mirror`, `tools/bootstrap_artifact_release.py` | `cache-hygiene` | Cache surface changes — apply the seven invariants. |
| `tools/initialize` | `initialize`, `bootstrap-product`, `doc-sync` | Idempotent. Update `bootstrap-product` SKILL.md when adding steps. |
| `tools/agent`, `tools/agent_kb*.py`, `tools/agent_kb_tests/**` | `knowledge-management`, `doc-sync` | Validate with KB rebuild + tests. |
| `tools/agent_check`, `tools/agent_check.py`, `tools/agent_check_tests/**` | `doc-sync` | Validate with `./repo.sh agent_check --stale-only`. |
| `tools/setup`, `tools/git_hooks/**` | `doc-sync` | Validate with `./repo.sh setup --status`. |
| `tools/source_mirror`, `tools/bootstrap_artifact_release.py` | `doc-sync` | Cache-miss paths must remain non-fatal. |
| `.github/workflows/**` | `doc-sync` | Re-check command ordering and cache keys. |
| *any architecture / refactor / new module discussion* | `improve-codebase-architecture`, `design-an-interface`, `domain-model` | Pair with `CONTEXT.md` updates inline. |
| *any feature build or bug fix* | `tdd`, `simplify` | Red-green-refactor; simplify before PR. |
| *any hard-to-reverse decision* | `decision-record` | Append a numbered ADR. |
| *bug report* | `triage-issue` | File issue with TDD fix plan. |
| *plan / spec / PRD breakdown* | `to-issues` | Vertical slices, tracer bullets. |
| *refactor request* | `request-refactor-plan` | Tiny-commit plan as an issue. |
| *plan stress-test* | `grill-me`, `domain-model` | Interview to resolve every branch. |
| *any git operation* | `git-style` | Mirror commit shape; never force-push to `main`. |
| *fork template into a new product* | `initialize`, `bootstrap-product` | Run `./repo.sh initialize`. |

## Tool-specific agent settings

- Claude local permissions live in `.claude/settings.local.json`.
- Codex permission prefixes live in `$CODEX_HOME/rules/default.rules`.
- Copilot repo instructions, when added, live in
  `.github/copilot-instructions.md`.

## Caveman

Caveman mode is the default communication style in this repo for all
agents. See `AGENTS.md` §1 and `.agents/skills/caveman/SKILL.md`.
