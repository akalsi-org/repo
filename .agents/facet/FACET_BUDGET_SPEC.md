# Facet Budget Command Spec

## Purpose

`./repo.sh facet budget` reports path/command/check sprawl per Facet. Helps operators identify:
- Facets with too many unrelated commands (should split).
- Facets with deep path ownership (should consolidate).
- Facets with stale or inactive checks.

## Output Format

CSV table (sortable):

```
facet,owner,status,paths,commands,checks,burden,last_touched,sprawl_flag
root,root,active,9,3,5,M,2026-04-26,OK
ideas,ideas,active,4,8,6,M,2026-04-26,HIGH_COMMANDS
maintenance,maintenance,active,3,2,4,L,2026-04-26,OK
bootstrap,root,active,6,2,3,H,2026-04-20,STALE
```

Columns:
- `facet`: Facet name (from .agents/facet/<name>/facet.json).
- `owner`: Owner field from facet.json.
- `status`: active|archived (from facet.json or OWNERSHIP.md).
- `paths`: Count of globs in facet.json `write_scope`.
- `commands`: Count of `commands` in facet.json.
- `checks`: Count of `checks` in facet.json.
- `burden`: H|M|L from OWNERSHIP.md (or inferred from command count: >5=H, 2–4=M, 1=L).
- `last_touched`: Date from OWNERSHIP.md `last_touched` or git log.
- `sprawl_flag`: OK | HIGH_PATHS | HIGH_COMMANDS | STALE | NO_OWNERSHIP.

## Sprawl Thresholds

- `HIGH_COMMANDS`: >5 unrelated commands (suggests split).
- `HIGH_PATHS`: >8 disjoint path globs (suggests consolidation or review).
- `STALE`: last_touched >90 days old.
- `NO_OWNERSHIP`: No OWNERSHIP.md or facet.json missing.

## Validation Rules (for agent_check)

1. Every Facet must have a facet.json.
2. Every Facet with paths must have an OWNERSHIP.md (with owned-paths section).
3. Every command must be owned by exactly one Facet (no multi-owner, no orphans).
4. Every check in facet.json must be runnable (fail loud if not).

## Integration with Agent_Check

```
./repo.sh agent_check --budget
  → runs `facet budget`, reports sprawl flags, exits 0 if no HIGH_* or STALE >180d.
  
./repo.sh agent_check --stale-only
  → reports STALE Facets + stale skill gates (>180d) + stale targets (proved_idle + review_due passed).
```

## Example Interpretation

If `ideas` reports `HIGH_COMMANDS`, COO + CEO should ask:
- "Are 8 ideas commands truly related, or should we split into ideas + backlog Facets?"
- "Can any commands move to maintenance or root?"

If `bootstrap` reports `STALE`, CFO + CTO should ask:
- "Is bootstrap phase done, and we can archive this Facet?"
- "Or do we need to re-review bootstrap/tools specs?"
