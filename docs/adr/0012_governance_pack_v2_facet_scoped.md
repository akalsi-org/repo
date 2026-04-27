# ADR-0012: Governance Pack v2 — Facet-Scoped Budget + Delegation

**Status:** Proposed  
**Decided:** 2026-Q2  
**Driver:** Template steering  
**Approver:** CEO, CFO  

---

## Context

After landing P0s (facet validation, scorecard, gates, fork playbook) and P1s (facet budget hard gate, activation receipt), operational experience reveals two governance challenges:

1. **Centralized budget ledger doesn't scale**: Board cycles are 4-week cadence; team needs differ per Facet (bootstrap spends fast, maintenance steady, ideas variable). Template cannot impose one budget model across all forks.

2. **Delegation is ad-hoc**: When bootstrap team needs to spend 40% more on binary curation, approval path is undefined. Should they escalate to CEO? CFO? Their own team lead? No declarative structure.

**Observation**: Facets already own paths, commands, checks. Natural extension: Facets declare their own governance (budget + delegation + escalation rules).

---

## Problem

**Current state**:
- Budget tracked in `.agents/repo.json` (single knob, all Facets share).
- Approvers hardcoded in board procedure docs (ad-hoc, not machine-readable).
- Fork has no way to override budget per Facet without forking Template governance logic.
- Products can't declare risk bands or escalation policies.

**What governance pack v1 (if it existed) would do**:
- Single centralized budget ledger, all Facets consume.
- Board decides all spend; team autonomy lost.
- Fork must choose: inherit all governance or define custom (no selective override).

**What governance pack v2 proposes**:
- Each Facet declares `.agents/facet/<name>/governance.json` (budget, approver, escalation, risk bands).
- Fork inherits Template governance.json per Facet; selectively overrides per strategy.
- Tools validate governance declarations; CI enforces hard gates if enabled.
- Scales: multi-team orgs can delegate to team Facets; small teams use centralized root.

---

## Decision

**Governance pack v2**: Facets own budget + delegation rules. Schema in `.agents/facet/GOVERNANCE_SPEC.md`.

### Structure

Each Facet declares optional `governance.json`:

```json
{
  "schema_version": "2",
  "budget": { "max_spend": "120 days", "period": "annual", "currency": "days" },
  "delegation": {
    "approver_facet": ["root"],
    "decision_latency_sla": "1 day",
    "escalation_policy": { "cost_ceiling": "30 days", "impact_ceiling": "high" }
  },
  "decision_raci": { "driver": "bootstrap", "approver": "root", "inputs": [...], "informed": [...] },
  "risk_bands": { "low": "LOE < 1d", "medium": "1d-3d", "high": "> 3d" },
  "activation_gate": { "enabled": true, "blocks_activation_at_budget": "90%" }
}
```

### Key principles

1. **Facet autonomy**: Each Facet declares its own rules; no central override (unless root).
2. **Template baseline**: Products inherit Template governance.json for all Facets. Fork can override selectively (e.g., change root `max_spend` from 500d to 200d; keep decision_raci unchanged).
3. **Declarative not executable**: governance.json is data, not code. Tools consume it; no plugins.
4. **Optional enforcement**: Facets without governance.json are ungoverned (infinite budget, no escalation). Fork chooses which Facets are gated.
5. **Fork inheritance pattern**:
   - Template declares baseline for each Facet.
   - Fork's governance.json inherits + overrides only fields listed in `allowed_overrides`.
   - Produces clear, auditable governance policy per product.

---

## Rationale

### Why decentralize?

- **Scales to multi-team orgs**: Each team Facet owns its budget; no central board bottleneck.
- **Decouples autonomy from board cycles**: Team can adjust escalation SLA (1d → 4h) without CEO approval.
- **Forks can customize**: Small bootstrap-heavy Product uses one policy; another product with long-running maintenance uses different policy.
- **Clear responsibility**: Facet declares its own governance; no ambiguity about who approves what.

### Why schema_version: "2"?

- Future migrations (v3: shared budget pools, v4: cross-Facet spend tracking) will exist.
- schema_version gates parser behavior; v2 tools reject v3 gracefully.
- No "default" backward-compat debt; v2 is explicit, breaking change is intentional.

### Why Facet-namespaced, not centralized ledger?

**Rejected**: Centralized `budget_ledger.json`:
```json
{
  "bootstrap": { "max_spend": "120 days", "approver": "root" },
  "ideas": { "max_spend": "80 days", "approver": "root" },
  ...
}
```
- Pros: Single source of truth for budget snapshot.
- Cons:
  - Loses team ownership signal (bootstrap team doesn't "own" their budget declaration).
  - Fork must override entire ledger or nothing (no selective per-Facet override).
  - Doesn't scale to delegated governance (different approvers per Facet requires conditional logic).
  - Conflicts with facet.json philosophy (Facets are self-describing).

---

## Implications

### Implementation phase (Q2 2026)

1. **Tools**:
   - Add `./repo.sh agent_check --governance` validation (schema, undefined approvers, cycles).
   - Add `./repo.sh facet budget --with-governance` (risk_band, escalation_ceiling columns).
   - Add `./repo.sh governance report` (JSON + Markdown dashboards).

2. **CI**:
   - Optional: PR check blocks merge if Facet budget exceeded + `activation_gate.enabled=true`.
   - Requires spend tracking DB (out of scope for v2 spec).

3. **Template**:
   - Add governance.json to all Facets (root, bootstrap, ideas, maintenance, etc.).
   - Baseline budgets based on historical patterns + Tier lifecycle (ADR-0011).
   - Fork inherits all; no action required unless custom policy desired.

4. **Documentation**:
   - `.agents/facet/GOVERNANCE_SPEC.md` (this spec).
   - `.agents/facet/GOVERNANCE_EXAMPLES.md` (three fork templates).
   - AGENTS.md § 7 (Integrations): governance pack v2 contract.

### Backward compatibility

- governance.json is **optional** per Facet. Facets without it are ungoverned.
- Existing Products (without governance.json) continue to work.
- No breaking change; pure addition.

---

## Acceptance tests

1. **Schema validation**: `./repo.sh agent_check --governance` passes for Template + all test forks.
   - ✅ governance.json structure matches spec.
   - ✅ approver_facet names exist in `.agents/facet/`.
   - ✅ No cycles in delegation (A→B→C doesn't loop back).

2. **Fork customization**: Small-fork template sets max_spend 60d (vs Template 500d).
   - ✅ Fork governance.json inherits v2 schema, baseline risk_bands.
   - ✅ Fork can override max_spend; other fields locked (unless in allowed_overrides).
   - ✅ Merged fork's governance.json is coherent (no undefined approvers).

3. **Budget enforcement**: If `activation_gate.enabled=true`, Facet blocks new ideas when spend >= 90%.
   - ✅ `./repo.sh facet budget --with-governance` flags Facet at 90%+ spend.
   - ✅ Manual gate implemented (tooling in next phase); operator can verify before merging.

4. **Delegation SLA checkable**: Operator can query governance.json to confirm escalation SLA.
   - ✅ `./repo.sh governance report` outputs decision_latency_sla per Facet.
   - ✅ Report is queryable (JSON export for board dashboards).

---

## Rejected alternatives

### Alternative 1: Centralized budget ledger (see Rationale above)
- **Rejected**: Loses team ownership, doesn't scale to delegated governance, conflicts with facet.json philosophy.

### Alternative 2: Governance as Facet RACI table in facet.json
- **Rejected**: Mixing declarative (Facet metadata) with governance (approval rules) in one file creates coupling.
- **Why separate?**: Facet definitions are stable (own paths, commands, checks). Governance policies are reviewed quarterly (budget cycles, team changes). Separation allows independent evolution.

### Alternative 3: No schema_version; assume tools are always v2-aware
- **Rejected**: Makes future migrations harder. schema_version gates parser; clearer error messages for mismatches.

---

## Related ADRs

- **ADR-0007: Facets for repo capabilities**: Facets own paths, commands, checks (baseline).
- **ADR-0011: Skills portfolio lifecycle tiers**: Tier 1/2/3 skills; governance v2 can reference tier for budget allocation.

---

## Timeline

- **Now (Decided 2026-Q2)**: Spec + ADR finalized.
- **Q2 2026**: Implementation phase (tools, CI integration, Template governance.json).
- **Q3 2026**: Adoption trial with 2–3 early fork products.
- **Q4 2026**: GA. All new forks receive governance pack v2 baseline.

---

**Status:** Ready for board review + approval.
