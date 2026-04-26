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
CEO first sets the current vision frame: what world the repo is trying
to move toward, what near-term target matters, and what trade-offs are
currently acceptable. Each advisory role must then run a brief
role-scoped `ideate` pass against that vision: generate options across
short/medium/long/visionary where credible, name 1st/2nd-order
effects, map each option to the CEO vision, then narrow to top 3
priorities. CEO does not count raw brainstorm volume as signal; role
must filter ideas through its mandate and the vision frame.

- **CEO**: parent agent. Owns final call. Balances vision, velocity,
  cost, risk, and user preference. Sets the vision frame before role
  ideation. May overrule all roles.
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

## Role-Scoped Ideation (Mandatory)

Before advisory ideation, CEO states:

- Vision: desired future repo capability.
- Near-term target: measurable next improvement.
- Trade-offs: what to optimize, what to refuse.

**Then each role MUST run ideate skill** (not just brainstorm; use the ideate
sub-agent). Roles generate portfolio across short/medium/long/visionary
horizons, name 1st/2nd/3rd-order effects, then filter to top 3 board priorities.

Each role ideation scope:

- **COO**: execution options. Backlog flow, WIP, checks, CI bands,
  maintenance cadence, queue readiness. 1st-order: velocity, process waste.
  2nd-order: skill adoption, operator autonomy, cost.
- **CTO**: architecture options. Facet contracts, ADR impacts,
  schemas, no-fallback machinery, interfaces, tests. 1st-order: correctness,
  coupling. 2nd-order: fork portability, product extensibility.
- **CFO**: cost/control options. Go-live cost, maintenance budget,
  CI/cache cost, tool sprawl, reversibility. 1st-order: cash outflow, risk.
  2nd-order: team burden, operator context.
- **CPO**: product/vision options. Template identity, Product fork
  value, autonomy story, idea/backlog/vision balance. 1st-order: user
  clarity, narrative coherence. 2nd-order: fork retention, contributor
  activation.
- **Chief of Staff** (if full-board): process options. Ideates *after*
  other roles so process wraps the options already surfaced. Decision gates,
  DACI shape, owner Facets, target/check fields, priority cadence. Maps
  each process idea back to vision. If single-role mode, ideates first.

Each role ideate sub-agent output must include:

- 3-6 candidate ideas (short/medium/long/visionary horizons where credible).
- 1st/2nd/3rd-order effects for each candidate.
- Vision mapping: how each candidate advances CEO vision frame.
- Top 3 priorities after filtering through role mandate.
- 1 stop-line risk (what would block this priority's success).

**Sub-agents operate caveman mode.** Ideate skill called with repo priors
(CONTEXT.md, ADRs, current Facet state, goals). Output becomes board input.

## Meeting Agenda

1. **Context packet & vision frame**
   - Active git changes.
   - Current ready ideas + stale/blocked decisions.
   - Relevant ADR constraints + Facet ownership concerns.
   - CEO states vision + near-term target + trade-off appetite.

2. **Role ideation (parallel, mandatory)**
   - Spawn all role sub-agents concurrently. Each runs ideate skill
     scoped to role (COO=execution, CTO=architecture, CFO=cost, CPO=product).
   - Roles generate 3-6 candidates (short/medium/long/visionary where credible),
     1st/2nd/3rd-order effects, vision mapping, then distill to top 3 priorities.
   - Each role surfaces 1 stop-line risk.
   - All sub-agents operate caveman mode.

3. **Board synthesis**
   - Collect all role portfolios. Visualize as table:
     ```
     | Horizon | COO | CTO | CFO | CPO | Consensus |
     |---------|-----|-----|-----|-----|-----------|
     | Short   | ... | ... | ... | ... | <cross-role themes> |
     | Medium  | ... | ... | ... | ... |  |
     | Long    | ... | ... | ... | ... |  |
     | Vision  | ... | ... | ... | ... |  |
     ```
   - Identify cross-role overlaps (e.g., 3+ roles proposed same theme).
   - Identify dissent (e.g., CFO cost risk vs CPO user value opportunity).

4. **Executive debate**
   - Each role name top 3 filtered priorities from their ideate.
   - Each role surface 1 stop-line risk.
   - CEO ask: what would make this priority wrong?
   - Record disagreements; do not smooth.

5. **CEO decision**
   - Pick 3-5 priorities max (prefer cross-role consensus themes).
   - For each priority: owner Facet, target, expected check,
     appetite, first action, decision status.
   - If board divided on priority, escalate crux to user or deferr to next cycle.

6. **Repo integration**
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
- Has explicit safe-parallel work metadata: `parallel_mode`,
  `worktree`, and `write_scope`.
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
- Vision: <CEO frame>
- Trade-off appetite: <constraints>

## Role Ideation Portfolios

### COO (Execution)

| Horizon | Candidate | 1st-order effect | 2nd-order effect | Vision map |
|---------|-----------|------------------|------------------|------------|
| Short   | ... | ... | ... | ... |
| Medium  | ... | ... | ... | ... |

**Top 3 priorities:** <filtered by role mandate>
**Stop-line risk:** <execution blocker>

### CTO (Architecture)

<same format>

### CFO (Cost)

<same format>

### CPO (Product)

<same format>

## Cross-Role Synthesis

| Horizon | Consensus theme | Roles | Dissent |
|---------|-----------------|-------|--------|
| Short   | <cross-role overlap> | <count> | <if any> |
| Medium  | <...> | ... | <...> |

## CEO Decision

| Priority | Owner Facet | Appetite | Target | Check | State | Rationale |
|----------|-------------|----------|--------|-------|-------|-----------|
| <from ideate portfolios, prefer consensus> | ... | days | ... | ... | queued | <why picked over alternatives> |

## Follow-Ups

- <priority> → `<skill>` or `./repo.sh ideas ...`
```

## Rules

- CEO decides. Board advises.
- Max 5 priorities. More means no priorities.
- Disagreement must be visible.
- No permanent process without repo artifact.
- No new Facet unless it owns paths/checks/docs.
- No issue/worktree until idea passes readiness gate.
- No parallel execution without separate worktrees and disjoint
  `write_scope` globs. `serial` items run alone unless CEO explicitly
  overrides.

## Implementation: How Parent Runs This Skill

1. **Read context** (this is done before invoking sub-agents).
   - Capture vision + trade-off frame.
   - Gather CONTEXT.md + ADRs + current ideas + Facet state.

2. **Spawn role sub-agents in parallel** (all at once via task tool).
   - Each sub-agent: general-purpose agent, caveman mode.
   - Each receives: vision frame + role mandate (CTO=arch, COO=execution, etc) +
     repo priors (CONTEXT.md excerpts, relevant ADRs, Facet state, current
     ready ideas).
   - Each sub-agent **must call ideate skill internally**. Prompt template:
     ```
     You are the <Role Name> for this board pass.
     Role mandate: <describe what this role optimizes for>
     Vision frame: <CEO frame>
     Trade-off appetite: <what to optimize, what to refuse>

     Operate caveman mode. Use the ideate skill to generate a portfolio
     across short/medium/long/visionary horizons (where credible). For each
     candidate, show 1st/2nd/3rd-order effects and vision mapping. Then
     filter your ideate output to top 3 priorities aligned with your role
     mandate. Name 1 stop-line risk.

     Output: your top 3 priorities + stop-line risk.
     ```
   - Allow 60+ seconds per sub-agent (ideate can be slow).

3. **Collect role portfolios** as they complete.
   - Visualize cross-role overlaps (themes 3+ roles proposed).
   - Flag disagreements (e.g., CFO risk vs CPO opportunity).

4. **Parent synthesizes** (this session does this step).
   - Prefer priorities from cross-role consensus.
   - When board divided, escalate crux to user (use debate-and-decide)
     or defer priority to next cycle.
   - Pick 3-5 priorities max.
   - For each: owner Facet, target, check, appetite, rationale.

5. **Persist** via `ideas add|score|promote` or `decision-record` if ADR-level.

**Example parent prompt to sub-agent:**
```
You are the CTO on this board pass.

Vision frame: Make learning-ledger the canonical source of next-bet evidence
so operators never manually search ideas.jsonl for context.

Trade-off appetite: Prefer automation over manual process. Accept 3-day
dev cycle. Refuse always-on services.

Role mandate: Validate that ideas have clean Facet ownership, ADR
grounding, and testability. Identify architecture deep-end bets that
unlock future phases. Surface integration risks + schema changes + no-fallback
impacts.

Use ideate skill to generate a portfolio (short/medium/long/visionary).
For each idea, show:
- 1st-order effect: what directly improves with this idea?
- 2nd-order effect: what indirect consequences flow from it?
- 3rd-order effect: (if credible) what systemic behavior shifts?
- Vision map: does this advance the vision frame?

Ideate output: 3-6 candidates across horizons. Then filter to your top 3
priorities (short/medium/long, in order). Name 1 stop-line risk.

Operate caveman mode. Output: your top 3 + stop-line risk.
```
