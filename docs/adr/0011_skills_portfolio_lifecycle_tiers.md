# ADR-0011: Skills portfolio lifecycle tiers

**Status:** Accepted  
**Decided:** 2026-04-26  
**Driver:** Template steering  
**Approver:** CFO (cost), COO (operations)  

## Context

After 11 c-suite board cycles + activation scaffold + readiness hygiene implementation, operational experience revealed skill usage is **phase-specific, not universal**.

This session invoked only 6 of 21 skills (c-suite, caveman, git-style, decision-record, doc-sync, knowledge-management). Debate-and-decide earlier questioned whether the remaining 15 skills should be pruned to reduce cognitive overhead + maintenance burden.

## Problem

**Side A (keep all):** 21 skills enable extensibility; products on fork can activate skills as phases shift (bootstrap → redesign → debug → launch). Maintenance cost is zero if a skill is unused in this repo's active phase.

**Side B (prune to core):** Template should ship 8–10 core skills; 11 others are dead weight during normal operation. Routing overhead + maintenance debt grow as the skill set grows. Products extend on fork by adding custom skills.

**Key factual error in debate:** "11 unused skills" conflates "not invoked this session" with "unused universally." Skills like **bootstrap-toolchain**, **ideate**, **improve-codebase-architecture**, **triage-issue** are phase-specific (bootstrap time, redesign time, debug time) but essential when those phases activate. They're referenced transitively by other skills' internal logic (e.g., c-suite internally recommends ideate; decision-record recommends domain-model).

**Unresolved crux:** Side B's maintenance concern is valid: skill gates can rot if not actively reviewed. Side A assumes "zero maintenance," but that's only true if gates stay synchronized with CONTEXT.md + ADRs.

## Decision

**Hybrid:** Keep all 21 skills. Add mandatory maintenance gates to prevent rot.

1. **Tier 1 (Core):** Always active; used every session.
   - caveman, git-style, decision-record, c-suite, tdd, knowledge-management

2. **Tier 2 (Phase-Specific):** Active during specific repo phases.
   - ideate, grill-me, design-an-interface, improve-codebase-architecture, domain-model, debate-and-decide (design/decision phases)
   - bootstrap-toolchain, cache-hygiene, bootstrap-product, initialize (bootstrap phase)
   - triage-issue, request-refactor-plan, simplify (debug/refactor phase)
   - to-issues, doc-sync (landing phase)

3. **Tier 3 (Template-Admin):** Operator-only, infrequent.
   - customize-cloud-agent (CI runner setup)

## Rationale

- **Extensibility preserved:** Products fork, inherit all skills, activate selectively per their lifecycle. No artificial pruning.
- **Maintenance gates added:** Each skill must list `gate_last_reviewed` date + owner Facet. Quarterly audit enforces synchronization.
- **Phase clarity:** Documenting tier prevents "why do I have this?" confusion. Reduces search space for operators in each phase.
- **Backward compatible:** No skills removed; no existing automations broken. Tiers are documentation + audit discipline, not hard constraints.

## Implications

1. Add `gate_last_reviewed` timestamp field to `.agents/skills/index.md` per skill (ISO-8601 date).
2. Add quarterly `agent_check` validation: flag skills with `gate_last_reviewed` >180 days old as stale.
3. Update AGENTS.md § 2.1 (Skills table) to annotate tier for each skill.
4. Document tier lifecycle in AGENTS.md § 3 (Maintenance contract).
5. Each skill's `.agents/skills/<name>/SKILL.md` must declare its tier in the header comment.

## Acceptance tests

- [ ] Tier 1 skills invoked ≥1× per board cycle (caveman, git-style, decision-record, c-suite).
- [ ] Tier 2 skills' gates remain synchronized with current ADRs + CONTEXT.md when audit runs.
- [ ] Quarterly audit runs; gates stale >180d are flagged by `agent_check --stale-gates`.
- [ ] New products fork; inherit all skills; document in README which tier matches their lifecycle phase.

## Rejected alternative

**Prune to 8–10 core skills, move others to product-level extensions.** This reduces template complexity but:
- Forecloses design + bootstrap + debug phases for new forks until they discover + re-implement.
- Increases per-product maintenance burden (each fork reinvents cache-hygiene, bootstrap-toolchain, triage-issue).
- Trading template simplicity for fork complexity; wrong boundary.

---

**Status:** Ready for landing in next board cycle.
