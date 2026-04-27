# Facet Governance Pack v2 Schema Spec

## 1. Overview

Governance pack v2 decentralizes budget, delegation, and escalation rules to individual Facets. Each Facet declares:
- **Budget**: Max spend (days/hours/cost/abstract units), period (monthly/quarterly/annual).
- **Delegation**: Approver Facet(s), decision latency SLA, escalation thresholds.
- **Decision RACI**: Driver, approver, inputs, informed parties.
- **Risk bands**: LOE thresholds for low/medium/high impact decisions.

**Rationale**: Facets own their own budgets + delegation rules, not centralized board. Scales governance to multi-team orgs. Decouples team autonomy from board cycles. Fork inherits Template governance, overrides selectively per product strategy.

---

## 2. Schema (governance.json)

### File location
`.agents/facet/<name>/governance.json`

### Complete schema

```json
{
  "schema_version": "2",
  "name": "bootstrap",
  "description": "Governance model for bootstrap Facet.",
  
  "budget": {
    "max_spend": "120 days",
    "period": "annual",
    "currency": "days",
    "note": "Pinned binary fetchers + tool spec logic."
  },
  
  "delegation": {
    "approver_facet": ["root"],
    "decision_latency_sla": "1 day",
    "escalation_policy": {
      "cost_ceiling": "30 days",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "bootstrap",
    "approver": "root",
    "inputs": ["maintenance", "ideas"],
    "informed": ["root"]
  },
  
  "risk_bands": {
    "low": "LOE < 1 day",
    "medium": "1 day <= LOE <= 3 days",
    "high": "LOE > 3 days"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "90%",
    "notifies": ["root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["max_spend", "period", "approver_facet", "decision_latency_sla"]
  }
}
```

### Field specifications

#### `schema_version` (string, required)
- Value: `"2"` (enables future migrations v3, v4…)
- Validates schema parser behavior.

#### `name` (string, required)
- Facet name (must match `.agents/facet/<name>/governance.json`).

#### `description` (string, optional)
- Human-readable purpose. Surfaced in reports.

#### `budget` (object, required)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `max_spend` | string | ✓ | e.g. "120 days", "500 hours", "50K USD" (literal unit in string). |
| `period` | enum | ✓ | "monthly", "quarterly", "annual", "project". |
| `currency` | enum | ✓ | "days", "hours", "cost" (e.g. USD/EUR/GBP), "abstract" (unitless). |
| `note` | string | | Justification / comments for operators. |

#### `delegation` (object, required)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `approver_facet` | string \| string[] | ✓ | Facet name(s) that approve decisions. "root" = Root Facet. |
| `decision_latency_sla` | string | ✓ | e.g. "1 day", "4 hours", "same-day" (human-readable). |
| `escalation_policy` | object | ✓ | See below. |

##### `escalation_policy` (object)

| Field | Type | Notes |
|-------|------|-------|
| `cost_ceiling` | string | Spend >= this triggers escalation (e.g. "30 days"). If null, no cost-based escalation. |
| `impact_ceiling` | string | Decisions with risk_band >= this escalate (e.g. "high", "medium"). If null, no risk-based escalation. |
| `fallback_approver` | string | Facet that approves when primary approvers unavailable (usually "root"). |

#### `decision_raci` (object, optional)

| Field | Type | Notes |
|-------|------|-------|
| `driver` | string | Facet that owns decision (usually self). |
| `approver` | string | Facet that approves (usually same as `delegation.approver_facet[0]`). |
| `inputs` | string[] | Facets consulted for input. |
| `informed` | string[] | Facets notified of decision (no veto). |

#### `risk_bands` (object, required)

| Field | Type | Notes |
|-------|------|-------|
| `low` | string | Definition of low-risk decision. Typically "LOE < 1 day". |
| `medium` | string | Definition of medium-risk. Typically "1 day <= LOE <= 3 days". |
| `high` | string | Definition of high-risk. Typically "LOE > 3 days". Can reference cost, blast radius, or other heuristics. |

#### `activation_gate` (object, optional)

| Field | Type | Notes |
|-------|------|-------|
| `enabled` | bool | If true, facet budget blocks activation (hard gate). |
| `blocks_activation_at_budget` | string | % or absolute value (e.g. "90%", "10 days remaining"). When exceeded, Facet cannot activate new ideas. |
| `notifies` | string[] | Facet names to notify when spend exceeds threshold. |

#### `fork_inheritance` (object, optional)

| Field | Type | Notes |
|-------|------|-------|
| `inherit_from_template` | bool | If true, Template governance.json is baseline for this Facet. |
| `allowed_overrides` | string[] | Which fields fork can override. If not listed, field is locked to Template value. |

---

## 3. Migration Path (v1 → v2)

### Option A: Gradual Opt-In (Recommended)
1. Template ships governance.json files for all Facets (schema_version: "2").
2. Products forking Template inherit governance.json unconditionally.
3. Existing Products can:
   - **Add governance.json per Facet** if they want governance enforcement.
   - **Omit governance.json** if Facet is ungovened (fallback: unlimited budget, no escalation policy).
   - **Migrate incrementally**: add governance.json to high-spend Facets first (bootstrap, ideas, maintenance).

### Option B: Dual-Schema Support (Enterprise)
1. Tools accept both v1 (if any legacy) and v2.
2. `agent_check --migrations` reports v1 usage.
3. Deprecation timeline: v1 support removed in 2027-Q4.

### Recommendation
**Go Option A.** Template ships v2 only. Products choose activation level per Facet. No fallback complexity for template; simpler for operators.

---

## 4. Fork Inheritance

### Baseline Template Governance
Template root facet defines:
```json
{
  "schema_version": "2",
  "name": "root",
  "budget": {
    "max_spend": "500 days",
    "period": "annual",
    "currency": "days"
  },
  "delegation": {
    "approver_facet": ["root"],
    "decision_latency_sla": "1 day",
    "escalation_policy": { "cost_ceiling": "100 days", "impact_ceiling": "high" }
  }
}
```

Other Facets (bootstrap, maintenance, ideas…) inherit and override as needed.

### Fork Override Patterns

#### Pattern 1: Conservative Fork (Small Team)
```json
{
  "budget": {
    "max_spend": "30 days",
    "period": "quarterly",
    "currency": "days"
  },
  "delegation": {
    "approver_facet": "root",
    "decision_latency_sla": "4 hours"
  }
}
```
- Tighter budget, faster decisions.
- Inherits `decision_raci`, `risk_bands`, `activation_gate` from Template.

#### Pattern 2: Decentralized Fork (Multi-Team)
```json
{
  "delegation": {
    "approver_facet": ["ideas", "maintenance"],
    "fallback_approver": "root"
  },
  "allowed_overrides": ["max_spend", "period", "approver_facet"]
}
```
- Team Facets approve for themselves; Root is fallback.
- max_spend can vary per product strategy.

#### Pattern 3: No Governance (Unlimited)
```json
{
  "governance": null
}
```
- Facet has no budget enforcement.
- Fallback: infinite spend, no escalation.

---

## 5. Validation & Tooling

### agent_check validation
```bash
./repo.sh agent_check --governance
  → Validates all governance.json files against schema.
  → Reports missing governance.json for Facets with `owns` paths.
  → Flags approver_facet names that don't exist.
  → Ensures no cycles in delegation (e.g., A approves B, B approves A).
  → Success: all governance.json valid, no undefined approvers.
```

### facet budget command (extended)
```bash
./repo.sh facet budget --with-governance
  → Adds "approved_by", "escalation_ceiling", "risk_band" columns.
  → Highlights Facets approaching activation gate.
  → CSV output for spreadsheet / BI ingestion.
```

### Governance report (future)
```bash
./repo.sh governance report
  → All Facets, budget status, delegation chain, risk band assignments.
  → JSON + Markdown formats.
  → Integration with board-level decision logs.
```

---

## 6. Examples by Product Scale

See `.agents/facet/GOVERNANCE_EXAMPLES.md` for three templates:
- Small fork (5 Facets, 90-day project, conservative budgets).
- Mid-market fork (10+ Facets, 12-month roadmap, cost-sensitive).
- High-velocity fork (unlimited Facets, per-team budgets, no central gate).

---

## 7. Open Questions

1. **Cost currency**: Should we accept "USD", "EUR", or just "cost" (abstract)?
   - Proposal: Accept any string; parser treats literally (no conversion).
   
2. **Budget roll-over**: Does unused budget in month N carry to month N+1?
   - Proposal: Depends on `period`. "monthly" = no roll-over (hard reset). "annual" = yes (cumulative).
   
3. **Shared budget pools**: Can multiple Facets share one budget?
   - Proposal: Out of scope for v2. Facets own individual budgets. Pool logic in v3 (collective budget + per-Facet allocations).

4. **Governance enforcement in CI**: Should CI block PR merge if Facet budget exceeded?
   - Proposal: Optional. `activation_gate.enabled=true` in facet.json enables CI check. Default: false (advisory only).

---

## Summary

Governance pack v2 moves budget + delegation from centralized board ledgers to Facet-owned declarations. Each Facet declares spend, approver, escalation rules, and risk bands. Template governance.json serves as baseline; Products override per strategy. Fork inheritance is selective, not all-or-nothing.

**Next phase**: Implementation (tools, CI integration, governance reports) in Q2 2026.
