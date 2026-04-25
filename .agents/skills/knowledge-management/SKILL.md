---
name: knowledge-management
description: Use when adding, querying, pruning, or designing repo-local knowledge captured in .agents/kb_src/, the agent KB, or skill routing entries.
---

# knowledge-management

Keep agent memory useful, inspectable, and cheap to regenerate.

## Workflow

1. **Query before writing.** Ask the KB whether a fact already exists
   for the path/verb you're about to record:

   ```
   ./repo.sh agent query probe --path <path> --verb <verb>
   ./repo.sh agent query request-brief --path <path> --request <text>
   ```

   If a row already covers it, edit that row instead of adding a
   duplicate.

2. **Durable inputs live in `.agents/kb_src/**/*.jsonl`.** One JSON
   object per line. Generated cache files do not belong in diffs.

3. **Stable facts go in `.agents/kb_src/core.jsonl`.** Larger
   structured collections go in `.agents/kb_src/tables/<name>.jsonl`
   when there are enough rows to justify a separate file.

4. **Runtime tables** under `build/agent_kb/runtime/` (or wherever the
   agent stores mutable state) are regenerated, not hand-edited.

5. **Keep entries action-oriented:**
   - what path/task they apply to,
   - what skill / check / ref they imply,
   - what command proves or queries the claim.

6. **Rebuild and validate:**

   ```
   ./repo.sh agent rebuild         # if the agent supports rebuild
   ./repo.sh agent_check --stale-only
   git diff --check
   ```

## Durable fact shape

Compact JSONL. Stable IDs.

```json
{"id":"fact_id","paths":["tools/**"],"verbs":["change"],"says":["Actionable guidance."],"skills":["doc-sync"],"refs":["AGENTS.md#commands"],"checks":["./repo.sh agent_check --stale-only"],"priority":80}
```

## Pruning rules

- A row earns its keep if a future agent acting on the matched
  path/verb would do something different because of it.
- If a row only restates what `AGENTS.md` already says, delete the
  row and let the doc be the single source.
- If a row says "do not X" but X is now structurally impossible
  (because of a check or refactor), delete the row.
- Stale > silent: when in doubt, edit the row to be accurate or
  delete it. Wrong rows mislead more than missing rows.

## Read first

- `AGENTS.md` skill table for current routing.
- `.agents/kb_src/core.jsonl` for fact examples.
- `.agents/skills/index.md` for path-pattern → skill routing.
