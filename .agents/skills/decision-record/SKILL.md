---
name: decision-record
description: Append a numbered ADR under docs/adr/ when a hard-to-reverse, surprising, trade-off-driven decision has been made. Use when the user says "record this", "ADR for X", or after a grilling session resolves a load-bearing call.
---

# decision-record

Capture decisions a future agent or human would otherwise re-derive.
Skip everything else — most calls are not worth recording.

## When to record

All three must be true:

1. **Hard to reverse.** Cost of changing your mind later is real.
2. **Surprising without context.** A future reader will look at the
   code and ask "why did we do it this way?"
3. **Result of a real trade-off.** Genuine alternatives existed; we
   picked one for specific reasons.

If any of the three is missing, do not record. A trivially-reversible
choice does not deserve an ADR.

## What qualifies

- Architectural shape (monorepo vs polyrepo, event-sourced vs CRUD).
- Integration patterns between subsystems (events vs sync HTTP).
- Technology choices that carry lock-in (DB, message bus, deploy
  target). Not every library — only ones that take a quarter to swap.
- Boundary decisions ("Customer data is owned by Customer; others
  reference by ID"). The explicit no-s are as valuable as yes-s.
- Deliberate deviations from the obvious path ("manual SQL, no ORM,
  because X"). Stops the next contributor from "fixing" intent.
- Constraints not visible in the code (compliance, latency budgets).
- Rejected alternatives when the rejection is non-obvious.

## Format

Files live in `docs/adr/` named `NNNN_slug.md` with sequential
numbering (`0001_…`, `0002_…`). Underscore separator (template
naming rule). Slug is short, lowercase.

Minimum body:

```md
# {Short title of the decision}

{1–3 sentences: context, what we decided, why.}
```

That's it. An ADR can be a single paragraph. The value is in
recording *that* a decision was made and *why*.

### Optional sections

Include only when they add value. Most ADRs won't need them.

- **Status** frontmatter (`proposed | accepted | deprecated |
  superseded by ADR-NNNN`) — useful when decisions are revisited.
- **Considered Options** — only when the rejected alternatives are
  worth remembering.
- **Consequences** — only when non-obvious downstream effects need
  to be called out.

## Workflow

1. Confirm the three criteria with the user (or yourself in autonomous
   mode).
2. Find the next number: `ls docs/adr/ | sort | tail -1` and add 1.
   The first ADR is `0001_…`.
3. Write the file. Keep it short.
4. Append a one-line entry to `docs/adr/index.md`.
5. Commit alongside the change the ADR documents — same commit when
   possible (`git-style`).

## Read first

- `docs/adr/index.md` for the existing decisions.
- `domain-model/ADR-FORMAT.md` for shape guidance shared with the
  domain-model skill.
