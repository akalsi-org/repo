# Skill Routing Index

Use the smallest skill set that matches the changed paths. This index
is agent-facing routing metadata; the actual procedures live in each
`.agents/skills/<name>/SKILL.md`.

| Path pattern | Skills | Notes |
|--------------|--------|-------|
| `AGENTS.md`, `README.md`, `CONTEXT.md`, `docs/adr/**`, `.agents/skills/index.md` | `doc-sync` | Run `./repo.sh agent_check --stale-only` and `git diff --check`. Keep skill table in sync with this index. |
| `.agents/facet/**` | `doc-sync` | Facets are repo-truth manifests. Run `./repo.sh agent_check --stale-only` and `git diff --check`. |
| `.agents/kb_src/**` | `knowledge-management`, `doc-sync` | Query before writing. Keep JSONL compact. |
| `.agents/skills/*/SKILL.md`, `.agents/skills/*/**.md` | `doc-sync` | New skill folders must appear in `AGENTS.md` skill table and (optionally) in this index. |
| `.agents/ideas/**`, `tools/ideas`, `tools/ideas.py`, `tools/ideas_tests/**` | `ideate`, `knowledge-management`, `doc-sync` | Idea inventory is canonical backlog-gate input. Validate with `./repo.sh ideas report` and ideas tests. |
| `repo.sh`, `bootstrap/**` | `bootstrap-toolchain`, `cache-hygiene`, `doc-sync` | Edits to fetch helpers or bootstrap planning do not bump cache key automatically — bump `bootstrap/vars/local_cache_key.sh:cache_epoch`. |
| `bootstrap/tools/*.sh` | `bootstrap-toolchain`, `cache-hygiene` | Edits naturally bump CI cache key via hashFiles. Declare `TOOL_DEPS` for bootstrap ordering and `TOOL_PRUNE_PATHS` for bloated toolchains. |
| `bootstrap/vars/local_cache_key.sh`, `.github/workflows/ci.yml`, `.github/workflows/cache_warm.yml`, `tools/source_mirror`, `tools/bootstrap_artifact_release.py` | `cache-hygiene` | Cache surface changes — apply the seven invariants. |
| `.agents/facet/maintenance/**`, `.github/workflows/cache_warm.yml` | `cache-hygiene`, `doc-sync` | Scheduled upkeep is maintenance Facet territory; cache warm must track CI cache keys and remain miss-tolerant. |
| `tools/initialize` | `initialize`, `bootstrap-product`, `doc-sync` | Idempotent. Update `bootstrap-product` SKILL.md when adding steps. |
| `tools/agent`, `tools/agent_kb*.py`, `tools/agent_kb_tests/**` | `knowledge-management`, `doc-sync` | Validate with KB rebuild + tests. |
| `tools/agent_check`, `tools/agent_check.py`, `tools/agent_check_tests/**` | `doc-sync` | Validate with `./repo.sh agent_check --stale-only`. |
| `tools/setup`, `tools/git_hooks/**` | `doc-sync` | Validate with `./repo.sh setup --status`. |
| `tools/source_mirror`, `tools/bootstrap_artifact_release.py` | `doc-sync` | Cache-miss paths must remain non-fatal. |
| `.github/workflows/**` | `doc-sync` | Re-check command ordering and cache keys. |
| *any architecture / refactor / new module discussion* | `improve-codebase-architecture`, `design-an-interface`, `domain-model` | Pair with `CONTEXT.md` updates inline. |
| *any feature build or bug fix* | `tdd`, `simplify` | Red-green-refactor; simplify before PR. |
| *any hard-to-reverse decision* | `decision-record` | Append a numbered ADR. |
| *contested load-bearing decision* | `debate-and-decide`, `decision-record` | Argue two defensible sides, escalate only preference-shaped cruxes, then record the decision. |
| *bug report* | `triage-issue` | File issue with TDD fix plan. |
| *plan / spec / PRD breakdown* | `to-issues` | Vertical slices, tracer bullets. |
| *refactor request* | `request-refactor-plan` | Tiny-commit plan as an issue. |
| *plan stress-test* | `grill-me`, `domain-model` | Interview to resolve every branch. |
| *brainstorm / roadmap / "what could we do about X"* | `ideate`, `domain-model` | Span all four horizons; classify 1st/2nd/3rd-order effects; recommend a portfolio. |
| *board meeting / executive review / CEO priorities / balance ideas backlog vision* | `c-suite`, `ideate`, `domain-model` | Run virtual board roles, surface disagreement, CEO picks 3-5 priorities, then persist through `ideas` when asked. |
| *contested load-bearing decision with no ADR resolution* | `debate-and-decide` | Two sub-agents argue opposing sides; parent escalates only preference-shaped cruxes to the user. |
| *any git operation* | `git-style` | Mirror commit shape; never force-push to `main`. |
| *fork template into a new product* | `initialize`, `bootstrap-product` | Run `./repo.sh initialize`. |
| `.agents/facet/core_infra/**`, `.agents/skills/core-infra-lead/**`, `bootstrap/providers/**`, `tools/infra/**`, `docs/adr/0014_core_infra_fabric.md` | `core-infra-lead`, `doc-sync` | Multi-provider VM fabric (ADR-0014). Re-read the ADR; never hard-code GitHub login/org; provider tokens stay at `~/<provider>.token`. |
| `.agents/personalities/**`, `.agents/skills/personality/**`, `.agents/facet/personality/**`, `tools/personality`, `tools/personality_pkg/**`, `tools/personality_tests/**` | `personality`, `doc-sync` | Multi-CLI persistent personalities (issue #14). Spec: `docs/research/multi_cli_personality_skill_spec.md`. Definitions committed; session state per-machine + gitignored. Never hard-code GitHub login/org in role bodies — use `<login>`/`<org>` placeholders. |

## Tool-specific agent settings

- Claude local permissions live in `.claude/settings.local.json`.
- Codex permission prefixes live in `$CODEX_HOME/rules/default.rules`.
- Copilot repo instructions, when added, live in
  `.github/copilot-instructions.md`.

## Skill Portfolio: Lifecycle Tiers + Gate Review Dates

See ADR-0011 for tier definitions. Gate_last_reviewed timestamps. Stale gates
(>180d old) trigger `agent_check --stale-only` warnings.

| Skill | Tier | Gate_last_reviewed | Status |
|-------|------|-------------------|--------|
| `caveman` | Core | 2026-04-26 | active |
| `git-style` | Core | 2026-04-26 | active |
| `decision-record` | Core | 2026-04-26 | active |
| `c-suite` | Core | 2026-04-26 | active (redesigned w/ mandatory ideate) |
| `tdd` | Core | 2026-04-26 | active |
| `knowledge-management` | Core | 2026-04-26 | active |
| `ideate` | Phase-Specific (design) | 2026-04-26 | active |
| `grill-me` | Phase-Specific (design) | 2026-04-26 | active |
| `design-an-interface` | Phase-Specific (design) | 2026-04-26 | active |
| `improve-codebase-architecture` | Phase-Specific (design) | 2026-04-26 | active |
| `domain-model` | Phase-Specific (design) | 2026-04-26 | active |
| `debate-and-decide` | Phase-Specific (design) | 2026-04-26 | active |
| `bootstrap-toolchain` | Phase-Specific (bootstrap) | 2026-04-26 | active |
| `cache-hygiene` | Phase-Specific (bootstrap) | 2026-04-26 | active |
| `bootstrap-product` | Phase-Specific (bootstrap) | 2026-04-26 | active |
| `initialize` | Phase-Specific (bootstrap) | 2026-04-26 | active |
| `triage-issue` | Phase-Specific (debug) | 2026-04-26 | active |
| `request-refactor-plan` | Phase-Specific (debug) | 2026-04-26 | active |
| `simplify` | Phase-Specific (debug) | 2026-04-26 | active |
| `to-issues` | Phase-Specific (landing) | 2026-04-26 | active |
| `doc-sync` | Phase-Specific (landing) | 2026-04-26 | active |
| `customize-cloud-agent` | Template-Admin | 2026-04-26 | active |
| `core-infra-lead` | Phase-Specific (infra/runtime) | 2026-05-01 | active |
| `personality` | Phase-Specific (infra/runtime) | 2026-05-01 | active |

Quarterly audit mandatory. Add gate_last_reviewed to all skill SKILL.md headers.
Run `./repo.sh agent_check --stale-gates` to flag >180d old gates.

## Caveman

Caveman mode is the default communication style in this repo for all
agents. See `AGENTS.md` §1 and `.agents/skills/caveman/SKILL.md`.
