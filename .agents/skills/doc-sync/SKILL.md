---
name: doc-sync
description: Use when a change may invalidate AGENTS.md, CONTEXT.md, docs/adr/, .agents/skills/index.md, .agents/kb_src/, README, or other repo-truth documentation.
---

# doc-sync

Keep repo truth current without turning docs into speculation.

## Repo-truth surfaces

| Surface | What it holds |
|--------|----------------|
| `AGENTS.md` | Maintenance contract, layout, commands, skill table, integrations, CI summary, subsystems table. |
| `README.md` | Human-facing entry point: what the product is, the verb surface, how to initialize. |
| `CONTEXT.md` | Domain language: the canonical terms and their relationships. |
| `docs/adr/NNNN_*.md` | Decision records: hard-to-reverse calls, with context. |
| `.agents/skills/index.md` | Path-pattern → skill routing. |
| `.agents/kb_src/core.jsonl` | Structured durable facts the agent KB consumes. |
| Nested `AGENTS.md` (per subsystem) | Deep guidance when root row is too dense. |

## Workflow

1. **Inspect the actual tree and code before editing docs.** Don't
   describe what you wish were true.
2. **Update `AGENTS.md`** for current contracts, layout, commands,
   policies, integrations, and subsystem facts. Keep it compact —
   move dense subsystem detail into nested `AGENTS.md`.
3. **Append to `docs/adr/NNNN_*.md`** for decisions a future agent
   would otherwise re-derive (use the `decision-record` skill).
4. **Update `CONTEXT.md`** when a domain term is sharpened or a new
   one is canonized (use the `domain-model` skill).
5. **Stitch skills:** any skill listed in `.agents/skills/index.md`
   must also appear in the `AGENTS.md` skill table, and any rule in
   `.agents/kb_src/core.jsonl` that names a skill must reference
   one that exists. `agent_check --stale-only` enforces these.
6. **Update the README** when the verb surface, integrations, or
   initialization steps change. The README is human; AGENTS.md is
   agent. Same facts, different framing.
7. **Validate:**
   - `./repo.sh agent_check --stale-only`
   - `git diff --check`
   - Run code checks only if code or generated outputs changed.

## Acceptance criteria

- AGENTS.md skill table is non-empty and matches `index.md`.
- Every skill folder in `.agents/skills/` is referenced by at least
  one row in either `index.md` or `kb_src/core.jsonl`.
- No row references a skill folder that does not exist.
- Integrations listed in AGENTS.md are mirrored in README.
- ADR numbers are sequential, no gaps, no duplicates.

## Read first

- `AGENTS.md` (whole file).
- `.agents/skills/index.md` for current routing.
- `.agents/kb_src/core.jsonl` for current rules.
