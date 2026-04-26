# CTO Ideation Session: Operator Autonomy via Durable Repo Truth

## Vision: Operator autonomy + audit trails on every decision; small Facet contracts > centralized orchestration; repo-local truth; 2-3 day cycles; no fallbacks for internal machinery.

## Frame
How do we harden durable repo truth so operators execute confidently across fork → scale → maintenance phases?

## Current State
- 28 ideas (all done/shaped/queued)
- 23 targets (archived, proved_idle)
- 27 learning-ledger rows (lessons from reviewed ideas)
- Skills: Tier 1 (Core) + Tier 2 (Phase-Specific) + Tier 3 (Admin)
- Facets: root, ideas, maintenance, commands
- Load-bearing: ADR-0006 (cache hygiene), ADR-0007 (facets), ADR-0010 (tool deps), ADR-0011 (skill tiers)

---

## SHORT HORIZON (days–2 weeks)

### S1: Facet schema as first-class closeout
1st: Facet JSON schema validated on every commit; breaking changes to manifest structure caught before landing.
2nd: Operators stop guessing which fields are executable vs hints; on-fork products inherit correct ownership contracts without ambiguity.
3rd: Products can lean on Facets as trustworthy API boundaries; vendor tools consume Facets directly instead of reading scattered AGENTS.md prose.

### S2: Learning-ledger picker tool
1st: Operator runs `repo.sh learning search --horizon medium --phase bootstrap` and gets filtered lessons from 27 reviewed ideas.
2nd: Next-bet synthesis (process-next-bet-synthesis) no longer searches chat; synthesis reads structured evidence; activation packets cite lessons directly.
3rd: Learning becomes a searchable corpus; new operators on-board fast; each decision surfaces relevant precedent.

### S3: Tier maintenance gate (ADR-0011 landing)
1st: `agent_check --stale-gates` flags skills with gate_last_reviewed >180d; blocks stale rotations in quarterly audit.
2nd: Operators know when a skill is out of sync with current ADRs; Phase-Specific tier skills don't rot unused.
3rd: Maintenance becomes auditable; each skill has owner + review date in `.agents/skills/index.md`; templates stay trustworthy on fork.

---

## MEDIUM HORIZON (1–3 months)

### M1: Write-scope conflict resolver
1st: Parallel work orchestration queries ideas.jsonl for overlapping write_scope; blocks unsafe parallel assignment; routes to board-safe decision.
2nd: Safe parallel work ceases to be manual DACI checklist; declared intents + write-scope globs become governance automation.
3rd: Products scale to 10+ parallel backlog items without CTO review of every conflict; repo truth (write_scope) drives orchestration.

### M2: Subsystem-facet bootstrap (forward-looking)
1st: Products define own subsystems via `.agents/facet/<subsystem>/facet.json` with nested AGENTS.md + checks; template core learns to emit subsystem ownership in commands + doc.
2nd: Forked products can split into bounded ownership (auth subsystem, data subsystem, etc) without re-hardening root facet schema.
3rd: Subsystems become first-class in CI/CD; bootstrap checks know which subsystem owns each check; idea backlog scopes to subsystem boundaries.

### M3: Evidence lineage for ideas
1st: Each idea row adds optional `evidence_source` (PR #, ADR, learning-ledger row id); operator can trace decision → activation → outcome → next bet.
2nd: Reviewers see full story; "why did we bet on this?" gets answered via click-through, not chat search.
3rd: Template credibility grows; external auditors can verify governance; products on-fork inherit lineage-first culture.

---

## LONG HORIZON (6–12 months)

### L1: Persistent Target ledger schema + query
1st: Add `schema_version`, `deprecation_path` to targets.jsonl; target queries expose targets that have aged without recent idea attachment.
2nd: Operators can deprecate stale targets explicitly; retired ideas no longer orphan targets; target lifecycle becomes visible.
3rd: Targets become true product fixtures; they don't evaporate; each product accumulates target wisdom; cross-product target reuse becomes feasible.

### L2: Facet-scoped CI (long lead)
1st: Product-owned Facets declare custom CI checks in facet.json; checks inherit Facet ownership + write-scope.
2nd: Template CI becomes product-pluggable; new subsystems land without touching root bootstrap/.github/workflows/.
3rd: Each product's CI is bespoke but governed; reduces CI-config drift; check ownership stays auditable.

---

## VISIONARY (1–3 years+)

### V1: Portable idea ledger → template → product lineage
1st: Ideas, targets, learning-ledger + ADRs ship with template as immutable baseline; products inherit best-practice decision history.
2nd: Product operators see "CEO bet on Facet ownership in 2024; that bet succeeded with these metrics; what does that mean for our subsystem?"
3rd: Becomes a multi-generational knowledge system; governance emerges from durable precedent, not from repeated debates; operators inherit institutional memory.

---

## EVALUATION

| Idea | Return | Time sink | Go-live cost | Maintenance | Reversibility | Strategic fit | Verdict |
|------|--------|-----------|--------------|-------------|---------------|---------------|---------|
| S1: Facet schema | H | L | L | M | H | H | Do now |
| S2: Learning picker | H | M | M | L | H | H | Do now |
| S3: Tier gates | M | L | L | L | H | H | Do now |
| M1: Write-scope conflict resolver | H | H | M | M | M | H | Design first |
| M2: Subsystem-facet bootstrap | H | H | H | H | M | H | Design first |
| M3: Evidence lineage | M | M | M | M | H | H | Do now |
| L1: Persistent target ledger | M | M | M | M | H | M | Watch |
| L2: Facet-scoped CI | H | H | H | H | L | H | Watch |
| V1: Portable idea lineage | H | M | M | L | L | H | Design first |

