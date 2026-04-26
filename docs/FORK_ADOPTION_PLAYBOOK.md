# Fork Adoption Playbook: Inherit-and-Tune

**For: New fork owners inheriting template governance.**

Forked but stuck? Here. Starts you in repo truth immediately without manual discovery. Template brings skills, Facets, and decision models — you tune them day 1.

---

## Section 1: Fork Activation

Run this once after clone. Idempotent. Sets product name, owner, license year.

```sh
./repo.sh initialize     # prompted: product name, owner, license year
./repo.sh                # opens subshell with REPO_* env vars
```

Verify renders:
- `LICENSE` — PolyForm Strict 1.0.0 header + copyright
- `README.md` — product name + quick-start verb table
- `CONTEXT.md` — product title (seeded stub; fill domain language later)
- `.agents/repo.json` — product knobs persisted
- `docs/adr/0001_template_adoption.md` — first ADR seeded

**Next:** Read `CONTEXT.md` top comment. That's where domain language lives. Add canonical terms + relationships as they emerge.

---

## Section 2: Inherit-and-Tune Governance

Template inherits governance via **Facets** + **Skills** + **Ideas**.

### Facet Structure

Facet = ownership declaration. Declares paths, commands, checks, docs.

Template Facets live in `.agents/facet/<name>/facet.json`:
- `root` — baseline template (README, CONTEXT, AGENTS.md, etc.)
- `bootstrap` — toolchain fetching, cache hygiene
- `skills` — all 20+ skills live here (routing via `.agents/skills/index.md`)
- `commands` — verb surface (all tools exposed via `./repo.sh`)
- `ideas` — idea inventory + targets (operating loop)
- `kb` — knowledge base facts (durable agent KB)
- `maintenance` — CI hygiene, doc sync, stale-idea reports
- `system_test` — repo-level cluster testing
- `git_hooks` — pre-commit hook source

**Tune:** Copy `.agents/facet/OWNERSHIP.md.template` → `.agents/facet/<facet-name>/OWNERSHIP.md` per Facet once you want to declare tier/ownership.

Template provides template; you fill owner/burden/status/blockers once Facet is active in your product.

### Tier-1 Skills (Always Active)

These run by default. All agents know them:
- `caveman` — terse comms (your default)
- `git-style` — git commits follow repo conventions
- `doc-sync` — docs stay in sync with code truth

### Tier-2 Skills (Phase-Scoped)

Activate per phase (design, execution, etc.). See `docs/SKILL_PHASES.md` for full map.

### Tier-3 Skills (Admin)

Owned by maintenance Facet + CEO decision:
- `c-suite` — exec board meetings
- `bootstrap-product` — fork this template into new product

---

## Section 3: Skill Phase Guide

Ref: `docs/SKILL_PHASES.md` (created from template).

**Phases:**
1. **Bootstrap** (day 0-1) — init, toolchain, seeds (must-have)
2. **Design** (week 1-2) — ideate, grill, model, debate (strategy formation)
3. **Execution** (ongoing) — tdd, simplify, refactor, triage (build + maintain)
4. **Landing** (pre-ship) — decision-record, doc-sync (finalize + consolidate)
5. **Operations** (post-launch) — c-suite rhythm, board cadence (governance)

Each phase has Tier-1 (always), Tier-2 (phase-scoped, optional but recommended), Tier-3 (admin).

---

## Section 4: First Ready Bet

Template seeds one **idea** on day 0: `product-shape-operating-loop`.

Lineage:
- Target: `product-operating-loop` (durable repo goal)
- Idea: `product-shape-operating-loop` (executable backlog item)
- State: `shaped` (ready to review + decide)
- Write scope: `.agents/ideas/**`, `.agents/targets/**`, `CONTEXT.md`
- Worktree: `required` (use separate git worktree)

**Activate first bet:**
```sh
./repo.sh ideas ready              # see full seeded shape
./repo.sh ideas activate <id>      # mark as active
./repo.sh                          # enter shell
cd .bare && git worktree add --detach ../worktree-<name> HEAD  # create worktree
cd ../worktree-<name>
# now edit ideas/targets/CONTEXT in your write scope
# run: ./repo.sh ideas close <id> --outcome "success" when done
```

**Outcome review:**
```sh
./repo.sh ideas report --cost       # see running ledger
# CPO/CEO scans: reversibility, maintenance, effect, checks
```

---

## Section 5: Board Cycle Rhythm

Governance gate-keeper: **c-suite** skill (CEO decision model).

**Monthly cadence** (example):
1. **Week 1** — `ideas ready` report + scoring (`reversibility`, `maintenance`)
2. **Week 1 (Thu)** — `./repo.sh c-suite` (exec board: ideas, backlog, vision, cost, Facet balance)
3. **Week 1 (Fri)** — CEO picks next 1-3 ideas to activate
4. **Week 2-4** — Execution (TDD, simplify, triage, refactor)
5. **Week 4** — `doc-sync` check + `decision-record` for load-bearing calls
6. **Repeat**

See: `.agents/facet/maintenance/` for cron jobs + CI integration.

---

## Checklist for Day 1

- [ ] Run `./repo.sh initialize` (provide product knobs)
- [ ] Verify LICENSE/README/CONTEXT/ADR render ✓
- [ ] Read CONTEXT.md top comment → add 3 domain terms + relationships
- [ ] Read `docs/SKILL_PHASES.md` → pick Tier-2 skills for design phase
- [ ] Review `.agents/repo.json` → knobs persisted ✓
- [ ] Optionally: copy `OWNERSHIP.md.template` to `.agents/facet/root/OWNERSHIP.md`
- [ ] Run `./repo.sh ideas ready` → see seeded bet
- [ ] Next: `./repo.sh c-suite` once you have 3+ ideas to score

---

## Links

- `CONTEXT.md` — Domain language (you edit)
- `docs/SKILL_PHASES.md` — Skill activation per phase
- `AGENTS.md` — Agent-facing contract + full skill table
- `.agents/facet/root/facet.json` — Root Facet ownership
- `.agents/ideas/ideas.jsonl` — Idea inventory (repo truth)
- `.agents/targets/targets.jsonl` — Target ledger (durable goals)
