# Skill Phases: Activation by Stage

**Map: Which skills activate in which phases? Tier 1/2/3 breakdown.**

Phases: Bootstrap → Design → Execution → Landing → Operations

---

## Phase 1: Bootstrap (Day 0-1)

**Goal:** Fork ready. Governance in place. First idea seeded.

### Tier 1 (Always)
- **caveman** — Terse comms active immediately
- **git-style** — Commits follow conventions

### Tier 2 (Bootstrap-Scoped, Recommended)
- **initialize** — Run once: `./repo.sh initialize`
- **bootstrap-toolchain** — Pinned tools fetch (`.local/toolchain/`)
- **doc-sync** — Verify docs in sync post-render

### Tier 3 (Admin)
- None (bootstrap is template-owned)

**Check:** `./repo.sh agent_check --stale-only` passes. LICENSE/README/CONTEXT render.

---

## Phase 2: Design (Week 1-2)

**Goal:** Shape strategy. Ideas emerge. Debate key calls. Model domain.

### Tier 1 (Always)
- **caveman** — Terse comms
- **git-style** — Commits

### Tier 2 (Design-Scoped, Core)
- **ideate** — Horizon portfolio (short/medium/long/visionary)
- **grill-me** — Stress-test plan via interview
- **design-an-interface** — Shape API/module contracts
- **debate-and-decide** — Load-bearing calls with two defensible sides
- **domain-model** — Stress test against CONTEXT.md + ADRs
- **knowledge-management** — Add durable facts to `.agents/kb_src/`

### Tier 3 (Admin)
- **c-suite** — CEO convenes board once ideas scored

**Cadence:** Week 1 → ideas ready report. Week 1 Thu → c-suite board picks next bets.

---

## Phase 3: Execution (Weeks 2-4, Ongoing)

**Goal:** Build. Maintain. Refactor safely. Ship features.

### Tier 1 (Always)
- **caveman** — Terse comms
- **git-style** — Commits

### Tier 2 (Execution-Scoped, Core)
- **tdd** — Test-driven development (red-green-refactor)
- **simplify** — After landing, tighten code
- **improve-codebase-architecture** — Find deepening opportunities
- **triage-issue** — Investigate bug + file TDD fix plan
- **request-refactor-plan** — Break refactor into safe incremental commits + file issue
- **to-issues** — Convert plan → independently-grabbable issues

### Tier 3 (Admin)
- None

**Cadence:** Continuous. Run `./repo.sh ideas ready` each sprint. Mark active. Close + record outcome.

---

## Phase 4: Landing (Pre-Ship, ~1 Week)

**Goal:** Consolidate. Finalize decisions. Docs match code.

### Tier 1 (Always)
- **caveman** — Terse comms
- **git-style** — Commits

### Tier 2 (Landing-Scoped, Required)
- **decision-record** — Hard-to-reverse calls → `docs/adr/NNNN_*.md`
- **doc-sync** — Ensure AGENTS.md, README, CONTEXT.md, docs/adr/ in sync
- **simplify** — Last code tightening before ship

### Tier 3 (Admin)
- None

**Check:** `git diff --check` passes. `./repo.sh agent_check --stale-only` passes. ADRs numbered sequentially.

---

## Phase 5: Operations (Post-Launch, Ongoing)

**Goal:** Sustain governance. Set cadence. Board reviews.

### Tier 1 (Always)
- **caveman** — Terse comms
- **git-style** — Commits
- **doc-sync** — Keep docs in sync (CI gated)

### Tier 2 (Operations-Scoped, Recommended)
- **c-suite** — Monthly exec board: ideas, backlog, vision, cost, Facet balance
- **knowledge-management** — Curate KB as domain evolves

### Tier 3 (Admin)
- **cache-hygiene** — Manage CI cache policy (maintenance Facet)
- **bootstrap-product** — Fork this template into new product (if multi-product org)

**Cadence:** Monthly c-suite. `ideas ready` report each sprint.

---

## Tier Definitions

| Tier | Access | Activation | Ownership |
|------|--------|-----------|-----------|
| **Tier 1** | All agents | Automatic. No opt-in. | Template (never disable). |
| **Tier 2** | All agents | Phase-scoped. Recommend per context. Agent can use if helpful. | Product (tune per phase). |
| **Tier 3** | Admin/CEO | Explicit gate. Facet-owned. Special permission. | Maintenance / Leadership (CEO decides). |

---

## Cross-Phase Themes

### Reversibility
Every idea scored `high`, `medium`, or `low` reversibility. Low-reversibility ideas need ADR + board approval before execution.

### Maintenance Burden
- `H` (High): 2+ days/week engineering care. CI gated. Proactive maintenance.
- `M` (Medium): ~1 day/week maintenance + review. Standard cadence.
- `L` (Low): Passive. Runs itself. Rare interventions.

Ideas with high maintenance must be approved by Facet owner before activation.

### Write Scope + Worktree

Every idea declares `write_scope` (glob patterns) + `worktree` (required/recommended/optional).

Safe parallel work only when:
1. Different worktrees
2. Write scope globs don't overlap
3. No item is `serial` (blockers)

Check: `.agents/ideas/ideas.jsonl` row 5-6.

---

## Example: Six-Month Timeline

```
Month 1 (Bootstrap + Design)
  ├─ Week 0: initialize. CONTEXT.md seeded.
  ├─ Week 1: ideate → 8 ideas. grill-me on top 3. design-an-interface for core API.
  ├─ Week 2: c-suite board picks idea-1-shape (design). debate load-bearing calls.
  ├─ Week 3: Start idea-1-execute. TDD loop. Keep CONTEXT.md current.

Month 2-3 (Execution)
  ├─ Sprint 1: idea-1 active. simplify after each feature.
  ├─ Sprint 2: triage bugs. Refactor with request-refactor-plan.
  ├─ Sprint 3: improve-codebase-architecture pass. Consolidate.

Month 4 (Landing)
  ├─ Pre-ship: decision-record all hard calls.
  ├─ doc-sync check. Agent_check stale-only.
  ├─ Final simplify. All ADRs numbered.

Month 5+ (Operations)
  ├─ Launch. Monthly c-suite cadence.
  ├─ Ideas backlog evolves. Board picks next bets.
  ├─ Knowledge-management: curate KB as domain deepens.
```

---

## Quick Ref: Activate Phase

```sh
# Design phase
./repo.sh ideas ready
# (see ideate + grill-me + design-an-interface candidates)

# Execution phase
./repo.sh ideas activate <id>  # mark shaped idea as active
./repo.sh tdd                  # start red-green-refactor
# (simplify, triage, refactor helpers available)

# Landing phase
./repo.sh agent_check --stale-only  # verify docs in sync
git diff --check                     # no trailing whitespace
# (decision-record any new ADRs)

# Operations phase
./repo.sh c-suite  # exec board meeting
./repo.sh ideas report --cost  # see full running ledger
```
