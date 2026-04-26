---
name: c-suite
description: Run a virtual executive board meeting with sub-agents to balance vision, idea inventory, backlog readiness, Facet ownership, maintenance cost, and execution priorities; the CEO makes the final priority call. Use when the user asks for a board meeting, executive review, CEO decision, priority setting, operating cadence, or balancing ideas/backlog/vision.
---

# c-suite

Run a strict, repo-local executive review. Goal: decide next priorities,
not create meeting theater.

## Operating Model Blend

This skill matches this repo owner's revealed preferences:

- Amazon-style mechanisms: customer/backward reasoning, ownership,
  frugality, bias for action, dive deep, disagree-and-commit.
- Netflix-style informed captain: broad dissent, one accountable
  decider, context not control, few good processes.
- GitLab-style handbook-first ops: single source of truth,
  transparency, iteration, boring solutions, measurable goals.
- Basecamp Shape Up: shape before betting, appetite over estimates,
  bounded cycles, clean bets.
- Toyota TPS: stop line on abnormalities, remove waste, incremental
  kaizen, make work easier, build quality into process.
- Atlassian DACI: driver gathers context, contributors advise,
  one approver decides, affected parties get informed.

Sources surveyed:

- Amazon Leadership Principles:
  `https://www.aboutamazon.com/about-us/leadership-principles`
- Netflix Culture Memo:
  `https://jobs.netflix.com/culture`
- GitLab Values Handbook:
  `https://handbook.gitlab.com/handbook/values/`
- Basecamp Shape Up:
  `https://basecamp.com/shapeup`
- Toyota Production System:
  `https://global.toyota/en/company/vision-and-philosophy/production-system/`
- Atlassian DACI:
  `https://www.atlassian.com/team-playbook/plays/daci`

## Read First

- `CONTEXT.md`
- `AGENTS.md`
- `docs/adr/index.md`
- `.agents/facet/*/facet.json`
- `.agents/ideas/ideas.jsonl` via `./repo.sh ideas list --json`
- Current repo state via `git status --short --branch`

If changed paths exist, run `./repo.sh agent_check` before deciding so
board sees active work, suggested skills, Facet owners, and closeout
checks.

## Board Roles

Spawn sub-agents when available and user asked for this skill. Keep
prompts narrow; each role returns priorities, risks, and vetoes.

- **CEO**: parent agent. Owns final call. Balances vision, velocity,
  cost, risk, and user preference. May overrule all roles.
- **COO**: execution flow. Looks at backlog, ready ideas, WIP, stale
  work, CI/check burden.
- **CTO**: architecture. Checks Facets, ADRs, ownership, interfaces,
  testability, no-fallback rule.
- **CFO**: cost. Scores go-live cost, maintenance overhead, cache/CI
  cost, tool sprawl, reversibility.
- **CPO**: product/vision. Tests ideas against Template/Product
  identity, user value, vision coherence.
- **Chief of Staff**: process. Enforces DACI shape: decision needed,
  owner, inputs, options, decision, follow-ups.

If sub-agents unavailable, simulate roles explicitly in sections. Do
not invent consensus. Surface disagreement.

## Meeting Agenda

1. **Context packet**
   - Active git changes.
   - Current ready ideas.
   - Stale ideas or blocked decisions.
   - Relevant ADR constraints.
   - Current Facet ownership concerns.

2. **Idea/backlog/vision balance**
   - Ideas: what should be shaped?
   - Backlog: what is ready to execute?
   - Vision: what long-horizon bet should constrain near work?
   - Maintenance: what upkeep must happen before new surface area?

3. **Executive debate**
   - Each role names top 3 priorities.
   - Each role names 1 stop-line risk.
   - CEO asks: what would make this priority wrong?

4. **CEO decision**
   - Pick 3-5 priorities max.
   - For each priority, name owner Facet, target, expected check,
     appetite, first action, and decision status.
   - Mark `decision_required=true` if contested or hard to reverse.

5. **Repo integration**
   - If user asked to persist, update `.agents/ideas/ideas.jsonl`
     through `./repo.sh ideas add|score|promote|park`.
   - If decision is hard to reverse, use `decision-record`.
   - If execution slices are needed, use `to-issues`.
   - If interface is unclear, use `design-an-interface`.

## Priority Filters

Prefer priorities that satisfy most:

- Advances explicit target or vision.
- Has one owner Facet.
- Has small first slice.
- Has cheap checks.
- Reduces maintenance burden or improves future autonomy.
- Reversible, unless clearly worth ADR-level commitment.
- Strengthens repo-local truth over chat-only process.

Reject or park priorities that:

- Add always-on services.
- Require vague human rituals with no repo artifact.
- Create multiple sources of truth.
- Depend on fallback behavior for internal machinery.
- Expand process without shrinking decision/execution cost.

## Output

```
## Context

- <facts read>

## Board Readout

| Role | Top Priority | Stop-Line Risk |
|------|--------------|----------------|
| COO | ... | ... |

## CEO Decision

| Priority | Owner Facet | Appetite | Target | Check | State |
|----------|-------------|----------|--------|-------|-------|
| ... | ... | days | ... | ... | queued/shaped/decision_required |

## Rationale

- <why these beat alternatives>

## Follow-Ups

- <priority> -> `<skill>` or `./repo.sh ideas ...`
```

## Rules

- CEO decides. Board advises.
- Max 5 priorities. More means no priorities.
- Disagreement must be visible.
- No permanent process without repo artifact.
- No new Facet unless it owns paths/checks/docs.
- No issue/worktree until idea passes readiness gate.
