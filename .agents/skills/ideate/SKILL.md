---
name: ideate
description: Generate a portfolio of ideas across short, medium, long, and visionary horizons, then classify each idea's downstream effects as 1st-order, 2nd-order, and (where credible) 3rd-order. Use when the user wants to brainstorm, explore options, sketch a roadmap, or pressure-test what a product or feature could become.
---

# ideate

Produce a deliberate, horizon-spanning idea portfolio with explicit
order-of-effect chains. Most "brainstorms" collapse to 5 short-horizon
1st-order ideas and miss everything strategic. This skill prevents
that collapse.

## When to engage

- "What could we do about X?"
- "Brainstorm features for Y."
- "Sketch a roadmap for Z."
- "What's the long-term play here?"
- After `grill-me` or `domain-model` resolves a load-bearing call —
  use ideate to populate what comes next.

## Core axes

### Axis 1 — Time horizon

Every idea lands in exactly one bucket:

| Horizon | Window | Cost gate | Shape |
|---------|--------|-----------|-------|
| **Short** | days–2 weeks | Within current capacity. No new infra. | Concrete features, fixes, or experiments shippable now. |
| **Medium** | 1–3 months | Requires planning, possibly new infra or hiring. | Capability bets — a new subsystem, a partnership, a measured rebuild. |
| **Long** | 6–12 months | Strategic commitment; multiple medium bets in service of it. | Positioning bets — what the product is for, who it serves, what it stops doing. |
| **Visionary** | 1–3 years+ | A narrative about the world the product wants to live in. | Identity bets — why anyone would care that you exist. |

If you cannot fill all four buckets, say so out loud. Empty
visionary ≠ "no vision"; it ≠ "ran out of words." Frame the gap.

### Axis 2 — Order of effect

For each idea, walk the effect chain:

| Order | What it captures | Example (for "add referral discount") |
|-------|------------------|----------------------------------------|
| **1st** | The direct, intended effect of doing the thing. | Existing users invite friends; some convert. |
| **2nd** | What the 1st-order effect causes downstream — behavior shifts, supply/demand response, knock-on costs. | Acquisition mix shifts toward referred users (different LTV, lower CAC); support volume changes shape; finance forecasting model gets noisier. |
| **3rd** | Emergent or systemic — competitive response, identity drift, regulation surfaces, second-derivative effects on culture or moat. | Competitors copy the program → industry-wide CAC compression; brand becomes "the discount one"; finance team builds dedicated cohort tooling that itself becomes a differentiator. |

Rules:

- Always state 1st order. Always.
- Always state 2nd order. If you cannot, the idea is too vague.
- State 3rd order **only when credible**. Speculation labeled as 3rd
  order is worse than no 3rd order. If unsure, write "3rd: not
  credible to call yet" and stop.
- Order ≠ time. A 1st-order effect at the visionary horizon is still
  1st-order. Don't conflate horizon and order.

## Optional evaluation axes

When the user asks to compare, rank, prioritize, classify, or sharpen
ideas, add a compact scoring pass after classification. Keep scores
directional; false precision is worse than no score.

Use `H/M/L` by default:

| Axis | High means | Watch for |
|------|------------|-----------|
| **Return** | Large upside if it works: leverage, revenue, learning, moat, or future optionality. | Calling an idea high-return without naming the mechanism. |
| **Time sink** | Large elapsed time or attention drain before useful feedback. | Ideas that look cheap but require repeated coordination. |
| **Go-live cost** | Expensive first release: infra, migration, tooling, docs, support, launch risk. | Hidden activation work after code is merged. |
| **Maintenance overhead** | Ongoing cost to keep it correct, useful, secure, and documented. | Load-bearing automation, stale generated output, or human-only rituals. |
| **Reversibility** | Easy to unwind without breaking users, docs, or Product forks. | Naming or layout choices that become contracts. |
| **Strategic fit** | Strongly reinforces the product identity and constraints already documented. | Cool ideas that stretch the domain language or reopen settled ADRs. |

For larger portfolios, include one more column:

| Verdict | Meaning |
|---------|---------|
| **Do now** | High return, low-to-medium cost, clear next action. |
| **Design first** | Promising but interface, ownership, or migration shape is unclear. |
| **Watch** | Interesting, but timing or evidence is weak. |
| **Avoid** | Cost, maintenance, or contradiction overwhelms upside. |

These axes are intentionally extensible. If the user's domain needs a
different lens, add a named temporary lens in the report, such as
`Regulatory exposure`, `Support burden`, `User trust`, `Data gravity`,
or `Distribution leverage`. Do not permanently expand this skill for
one-off lenses unless they recur across sessions.

## Process

### 1. Frame

Write one sentence stating what the user is choosing about. Read
`CONTEXT.md` and any obviously relevant `docs/adr/` entries before
generating. Constraint awareness sharpens ideas; ignorance produces
ideas the project has already rejected.

### 2. Generate per horizon

For each of the four horizons, produce 2–4 candidate ideas. Aim for
**radical difference within the horizon** — not three flavors of the
same thing. If you find yourself writing variants, replace one with
a contrarian angle (do less, drop the feature, reverse the polarity).

Don't pre-filter by feasibility; filter happens in step 4.

### 3. Classify

For every idea, write its 1st-order and 2nd-order effects. Add 3rd
order only when you can name a specific systemic mechanism, not a
vibes statement.

### 4. Score if requested

If the user asked for ranking, filtering, prioritization, cost
classification, or "best bets," score ideas against the optional
evaluation axes. Use `H/M/L`, plus a one-clause reason for any
surprising score. Prefer a table after the effect chains rather than
stuffing scores into each idea.

Do not let scoring replace effect chains. Scores summarize judgment;
they do not explain it.

### 5. Pressure test

Walk each idea against:

- `CONTEXT.md` glossary — is the idea consistent with the canonical
  terms, or does it stretch one?
- Existing ADRs — does it contradict a deliberate decision? If yes,
  flag it and either drop the idea or note the ADR as worth
  reopening.
- License + integrations — does it introduce a dependency the
  template forbids (e.g. CodeQL/Dependabot are excluded; permissive
  redistribution conflicts with PolyForm Strict)?
- Cache-hygiene + cost-cheap principles — does it require always-on
  paid infrastructure when an off-by-default alternative exists?

### 6. Recommend a portfolio

Pick a small set the user can actually carry: typically **2 short,
1–2 medium, 1 long, 1 visionary**. State why each made the cut and
what it depends on. Be opinionated — a menu without a recommendation
is half the work.

If scoring was requested, use the scores to justify the portfolio.
Explicitly call out any high-return idea you are not recommending
because it is a time sink, expensive to launch, high-maintenance, or
strategically distracting.

### 7. Offer next steps

For each chosen item, offer the right follow-up skill:

- Short / medium with a clear shape → `to-issues` (vertical-slice
  issues) or `tdd` (build-and-test).
- Medium / long that touches architecture → `design-an-interface` or
  `improve-codebase-architecture`.
- Anything load-bearing or hard-to-reverse → `decision-record`.
- Anything that survived a real trade-off in step 4 → `decision-record`
  for the rejected alternative.

## Output shape

Default report layout:

```
## Frame

<one-sentence problem statement>

## Constraints in scope

<bullets from CONTEXT.md, ADRs, license, integrations that bound the search>

## Short horizon (days–2 weeks)

1. <idea>
   - 1st: <effect>
   - 2nd: <effect>
   - 3rd: <effect or "not credible">

2. ...

## Medium horizon (1–3 months)

(same shape)

## Long horizon (6–12 months)

(same shape)

## Visionary (1–3 years+)

(same shape)

## Recommended portfolio

- Short: <picks + why>
- Medium: <picks + why>
- Long: <pick + why>
- Visionary: <pick + why>

## Next steps

- <item> → `<skill>` to <action>
```

When ranking was requested, add:

```
## Evaluation

| Idea | Return | Time sink | Go-live cost | Maintenance | Reversibility | Strategic fit | Verdict |
|------|--------|-----------|--------------|-------------|---------------|---------------|---------|
| <idea> | H/M/L | H/M/L | H/M/L | H/M/L | H/M/L | H/M/L | Do now / Design first / Watch / Avoid |
```

For brief sessions, the user can ask for "just the matrix" — a 4x3
table with horizon rows and 1st/2nd/3rd columns. Default is the full
layout.

## Anti-patterns

- **Five short ideas labeled "ideation."** If horizons aren't
  spanned, this skill failed. Force at least one entry per horizon
  or say "no credible visionary read yet" and explain why.
- **Variants masquerading as alternatives.** Three flavors of the
  same idea is one idea.
- **3rd-order garnish.** Adding a vague systemic claim because the
  format has a slot for it. Empty 3rd-order is honest; vapor 3rd-order
  is dishonest.
- **Order/horizon conflation.** "It's a 3rd-order idea because it's
  long-term." No — order is about the effect chain, horizon is about
  when. They're orthogonal.
- **Ignoring existing ADRs.** Re-suggesting something an ADR
  rejected, without acknowledging the ADR, wastes the user's time
  and corrodes trust in the skill.
- **Spreadsheet theater.** Scores without mechanisms create fake
  confidence. Every surprising `H` or `L` needs a reason.
- **Tool sprawl by brainstorm.** Do not create a new permanent
  ideation axis for a one-time concern. Treat lenses as local unless
  they recur.

## Read first

- `CONTEXT.md` for project terms.
- `docs/adr/index.md` for already-decided territory.
- `AGENTS.md` Integrations and license clauses for hard limits.
