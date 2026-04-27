# Facet Governance Pack v2: Examples

Three fork templates showing governance.json configurations for different product strategies.

---

## Example 1: Small Fork (5 Facets, 90-Day Project)

**Profile**: Early-stage startup. 3 engineers. Bootstrap phase only. Tight budget, fast decisions.

### Template `.agents/facet/root/governance.json`

```json
{
  "schema_version": "2",
  "name": "root",
  "description": "Project-scoped governance for lean startup (90 days, 5 engineers).",
  
  "budget": {
    "max_spend": "60 days",
    "period": "project",
    "currency": "days",
    "note": "90 days elapsed * 2 eng / 3 = 60 engineering days. Remaining bandwidth = customer work."
  },
  
  "delegation": {
    "approver_facet": "root",
    "decision_latency_sla": "4 hours",
    "escalation_policy": {
      "cost_ceiling": "5 days",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "root",
    "approver": "root",
    "inputs": ["bootstrap", "ideas"],
    "informed": []
  },
  
  "risk_bands": {
    "low": "LOE < 4 hours",
    "medium": "4 hours <= LOE <= 1 day",
    "high": "LOE > 1 day"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "80%",
    "notifies": ["root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": []
  }
}
```

### `.agents/facet/bootstrap/governance.json` (inherits, no override)

```json
{
  "schema_version": "2",
  "name": "bootstrap",
  "description": "Core bootstrap toolchain + infrastructure.",
  
  "budget": {
    "max_spend": "30 days",
    "period": "project",
    "currency": "days",
    "note": "50% of root budget. Includes fetch helpers, tool specs, worktree setup."
  },
  
  "delegation": {
    "approver_facet": "root",
    "decision_latency_sla": "same-day",
    "escalation_policy": {
      "cost_ceiling": "2 days",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "risk_bands": {
    "low": "LOE < 2 hours",
    "medium": "2 hours <= LOE <= 6 hours",
    "high": "LOE > 6 hours"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "85%",
    "notifies": ["root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": []
  }
}
```

### Key characteristics

- **Tight budget caps**: 60d total project, 30d bootstrap. No room for scope creep.
- **Fast SLAs**: 4-hour root, same-day bootstrap. Startup velocity.
- **Early escalation**: Ceiling 5d (root) / 2d (bootstrap). Triggers quickly.
- **No overrides**: Startup inherits Template v2 schema unchanged. Cannot go off-policy.

---

## Example 2: Mid-Market Fork (10+ Facets, 12-Month Roadmap, Cost-Sensitive)

**Profile**: Series B SaaS. 15 engineers across 3 teams (Bootstrap/Infra, Ideas/Product, Maintenance/Ops). Monthly budget reviews. Cost-tracking enabled.

### Template `.agents/facet/root/governance.json`

```json
{
  "schema_version": "2",
  "name": "root",
  "description": "Multi-team governance: per-Facet budgets, delegated approvals, cost-tracked.",
  
  "budget": {
    "max_spend": "400 hours",
    "period": "monthly",
    "currency": "hours",
    "note": "15 engineers * 1 sprint worth (40h). Includes 20% infrastructure overhead."
  },
  
  "delegation": {
    "approver_facet": ["ideas", "maintenance"],
    "decision_latency_sla": "1 day",
    "escalation_policy": {
      "cost_ceiling": "200 hours",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "root",
    "approver": "root",
    "inputs": ["ideas", "bootstrap", "maintenance"],
    "informed": []
  },
  
  "risk_bands": {
    "low": "LOE < 1 day",
    "medium": "1 day <= LOE <= 3 days",
    "high": "LOE > 3 days"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "90%",
    "notifies": ["root", "ideas", "maintenance"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["max_spend", "period", "approver_facet", "decision_latency_sla"]
  }
}
```

### `.agents/facet/ideas/governance.json` (override budget + SLA)

```json
{
  "schema_version": "2",
  "name": "ideas",
  "description": "Product development. Team lead = approver. Fast decisions on experiments.",
  
  "budget": {
    "max_spend": "160 hours",
    "period": "monthly",
    "currency": "hours",
    "note": "40% of monthly pool. Two engineers full-time on experiments + features."
  },
  
  "delegation": {
    "approver_facet": "ideas",
    "decision_latency_sla": "4 hours",
    "escalation_policy": {
      "cost_ceiling": "40 hours",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "ideas",
    "approver": "ideas",
    "inputs": ["maintenance", "bootstrap"],
    "informed": ["root"]
  },
  
  "risk_bands": {
    "low": "LOE < 4 hours",
    "medium": "4 hours <= LOE <= 1 day",
    "high": "LOE > 1 day"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "85%",
    "notifies": ["ideas", "root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["max_spend", "period"]
  }
}
```

### `.agents/facet/maintenance/governance.json` (override budget)

```json
{
  "schema_version": "2",
  "name": "maintenance",
  "description": "Ops + on-call + bug fixes. Steady spend, shared approvers.",
  
  "budget": {
    "max_spend": "120 hours",
    "period": "monthly",
    "currency": "hours",
    "note": "30% of monthly pool. One engineer + on-call coverage."
  },
  
  "delegation": {
    "approver_facet": "maintenance",
    "decision_latency_sla": "1 day",
    "escalation_policy": {
      "cost_ceiling": "60 hours",
      "impact_ceiling": "high",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "maintenance",
    "approver": "maintenance",
    "inputs": ["ideas"],
    "informed": ["root"]
  },
  
  "risk_bands": {
    "low": "LOE < 2 hours",
    "medium": "2 hours <= LOE <= 1 day",
    "high": "LOE > 1 day"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "90%",
    "notifies": ["maintenance", "root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["max_spend", "period"]
  }
}
```

### Key characteristics

- **Delegated approvals**: ideas + maintenance self-approve (4h + 1d SLA). Root is fallback.
- **Team budgets**: ideas 160h, maintenance 120h, bootstrap implicit (120h left). Clear allocation.
- **Monthly cadence**: Cost tracking per month. Easy to pair with accounting cycles.
- **Selective overrides**: Each Facet can change max_spend + period (strategic decision), but not approval chain.
- **Cost-sensitive**: 200h ceiling on root escalation. Cost control built in.

---

## Example 3: High-Velocity Fork (Unlimited Velocity, No Central Gate)

**Profile**: High-growth company. 50+ engineers across 8 teams. Distributed governance. No central budget cap (trusts team budgets).

### `.agents/facet/root/governance.json` (unlimited, no gate)

```json
{
  "schema_version": "2",
  "name": "root",
  "description": "Company-wide: no central gate. Teams own budgets. Root delegates.",
  
  "budget": {
    "max_spend": "unlimited",
    "period": "annual",
    "currency": "abstract",
    "note": "No company-wide hard cap. CFO tracks via spend-tracking system (separate from governance pack)."
  },
  
  "delegation": {
    "approver_facet": ["bootstrap", "ideas", "maintenance", "performance", "security"],
    "decision_latency_sla": "same-day",
    "escalation_policy": {
      "cost_ceiling": null,
      "impact_ceiling": "critical",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "root",
    "approver": "root",
    "inputs": [],
    "informed": []
  },
  
  "risk_bands": {
    "low": "LOE < 1 day",
    "medium": "1 day <= LOE <= 1 week",
    "high": "LOE > 1 week"
  },
  
  "activation_gate": {
    "enabled": false,
    "notifies": []
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["budget", "delegation", "risk_bands"]
  }
}
```

### `.agents/facet/ideas/governance.json` (team self-governs)

```json
{
  "schema_version": "2",
  "name": "ideas",
  "description": "Product team. Self-approving decisions. Escalates only if critical impact.",
  
  "budget": {
    "max_spend": "500 days",
    "period": "quarterly",
    "currency": "days",
    "note": "Negotiated per quarter with CPO. 20 engineers = ~500 days capacity."
  },
  
  "delegation": {
    "approver_facet": "ideas",
    "decision_latency_sla": "2 hours",
    "escalation_policy": {
      "cost_ceiling": null,
      "impact_ceiling": "critical",
      "fallback_approver": "root"
    }
  },
  
  "decision_raci": {
    "driver": "ideas",
    "approver": "ideas",
    "inputs": ["maintenance", "bootstrap", "security"],
    "informed": ["root"]
  },
  
  "risk_bands": {
    "low": "LOE < 4 hours",
    "medium": "4 hours <= LOE <= 3 days",
    "high": "LOE > 3 days"
  },
  
  "activation_gate": {
    "enabled": true,
    "blocks_activation_at_budget": "95%",
    "notifies": ["ideas", "root"]
  },
  
  "fork_inheritance": {
    "inherit_from_template": true,
    "allowed_overrides": ["budget", "period", "decision_latency_sla"]
  }
}
```

### Key characteristics

- **No central cap**: root max_spend = "unlimited". Teams manage their own ceilings.
- **Team autonomy**: ideas, maintenance, etc. are self-approving.
- **Escalation only on critical impact**: cost_ceiling = null (no cost-based escalation). impact_ceiling = "critical" (only catastrophic decisions escalate).
- **Fast SLAs**: same-day (root), 2h (ideas). High-velocity culture.
- **Quarterly budgets**: teams negotiate budget per quarter; governance pack reflects negotiated numbers.
- **Optional gates**: ideas has gate at 95% (team can see warning); root gate disabled (informational only).

---

## Migration Path Between Examples

### Small → Mid-Market (Example 1 → 2)

After 90 days, startup grows to Series A (15 engineers, 12-month horizon):

1. Remove `fork_inheritance.allowed_overrides: []` lock.
2. Split root budget 60d → 400 hours/month (scale time unit).
3. Create ideas + maintenance Facet governance.json (was absorbed into root before).
4. Add per-Facet approvers (ideas, maintenance self-approve).

**Backward compatible**: Old governance.json still valid; teams adopt new structure incrementally.

### Mid-Market → High-Velocity (Example 2 → 3)

After Series B, company scale mandates distributed governance:

1. Change root budget "unlimited" (remove hard cap).
2. Set `activation_gate.enabled: false` on root (optional advisory).
3. Keep per-team gates (ideas 95%, maintenance 90%).
4. Decentralize approvals (teams self-approve, root is fallback only).

**Operational shift**: Accounting system takes over budget tracking; governance pack becomes policy-of-record (not enforcement).

---

## Checklist: Choosing Your Governance Template

| Criterion | Small | Mid-Market | High-Velocity |
|-----------|-------|-----------|---------------|
| Team size | <5 | 10–20 | 50+ |
| Budget unit | days (time) | hours (time) + cost | abstract (policy, cost tracked separately) |
| Central gate | Hard cap (80%) | Soft cap (90%) | Disabled (advisory) |
| Approvers | All root | Team self + root fallback | Team self + root fallback |
| Decision SLA | Fast (4h–1d) | Moderate (1d) | Fastest (2h–same-day) |
| Override policy | Locked (template inherit only) | Selective (budget + SLA) | Unrestricted (full override) |
| Period | Project (90d) | Monthly | Quarterly |

---

## Next Steps

1. **Choose your template**: Pick the example closest to your product's profile.
2. **Copy + customize**: Replace team names, budget numbers, SLAs with your values.
3. **Validate**: Run `./repo.sh agent_check --governance` to check schema.
4. **Document**: Add notes to governance.json explaining why your choices differ from Template baseline.
5. **Share**: Distribute governance.json to your leadership for review; incorporate feedback.

---

## See Also

- `.agents/facet/GOVERNANCE_SPEC.md` (complete schema reference).
- `docs/adr/0012_governance_pack_v2_facet_scoped.md` (decision rationale).
- `AGENTS.md` § 7 (Integrations: governance pack contract).
