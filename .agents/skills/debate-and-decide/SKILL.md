---
name: debate-and-decide
description: Orchestrate two adversarial sub-agents to argue a load-bearing question from opposing positions, with the parent agent resolving what it can and escalating only preference-shaped cruxes to the user. Output is an ADR, an ADR for the rejected alternative when non-obvious, a new check or skill when a recurrence pattern was revealed, or any combination. Use when a decision is genuinely contested and not already settled by an existing ADR.
---

# debate-and-decide

Adversarial decision-making. Two sub-agents take opposite sides of a
contested question. Each is seeded with the project's priors and
operates in `caveman` mode. The parent agent collects arguments,
answers what it can from `CONTEXT.md` / `docs/adr/` / `kb_src` /
integrations, and escalates only the cruxes that are *preference-
shaped* — taste, risk-appetite, strategic direction — to the user.
The user is the tie-breaker, never the bottleneck.

## When to engage

All four must be true:

1. The decision is **load-bearing** by `decision-record`'s gate —
   hard to reverse, surprising without context, result of a real
   trade-off.
2. **No existing ADR resolves it.** If `docs/adr/` already settles
   the question, route to `domain-model` to apply that decision; do
   not re-litigate.
3. **At least two genuinely defensible positions exist.** If one
   side is obviously right, run `tdd` or `decision-record` directly.
4. The user explicitly asks, **or** the parent agent has hit a
   crux it cannot resolve from priors alone after one good-faith
   attempt.

If any of the four is false, do not invoke. The skill is heavyweight
on purpose; routine choices should not pay the orchestration cost.

## Architecture

```
                        Parent agent (this skill)
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   Sub-agent A       Sub-agent B          User
   (caveman, priors) (caveman, priors)   (tiebreaker, only on
                                          preference-shaped cruxes)
```

- **Parent agent** runs the procedure, owns the round budget, owns
  the escalation gate, owns the output artifacts.
- **Sub-agents** argue *opposing* positions on the *same* question.
  Both have read access to the priors. Both use `caveman` so token
  spend stays sane. Either may *call out* a question for the parent
  rather than fabricate an answer.
- **User** is invoked only when the parent cannot break a tie from
  facts available in the repo.

## Priors that seed every sub-agent

The parent must hand each sub-agent the same prior bundle:

- One-sentence framing of the question.
- The opposing-position assignment ("Side A: <stance>", "Side B:
  <stance>").
- Relevant `CONTEXT.md` excerpts (the canonical terms in scope).
- Titles + one-line summaries of `docs/adr/` entries that touch the
  area; the full body of any ADR that's load-bearing.
- Relevant rows from `.agents/kb_src/core.jsonl` (rules that match
  the affected paths/verbs).
- The Integrations table from `AGENTS.md` if credentials or external
  services are in scope.
- License clause summary if redistribution / commercial behavior is
  in scope.
- Allowed helper skills the sub-agent may consult (default:
  `caveman`, `domain-model`, `improve-codebase-architecture`,
  `cache-hygiene`, plus any others the parent thinks are load-
  bearing for the question).

Without seeding, sub-agents argue from training-data priors and
re-suggest things the project's ADRs already rejected. **Seeding is
mandatory.**

## Procedure

### 1. Gate-check (parent)

Walk the four "When to engage" conditions out loud (one sentence each).
If any fails, stop and route to the appropriate alternative
(`decision-record`, `domain-model`, `tdd`, `ideate`).

### 2. Frame (parent)

Write the contested question in one sentence. State the two
defensible sides. Pick which is "Side A" and which is "Side B"
deliberately; do not let the assignment be arbitrary because the
weaker side will receive less rigor.

### 3. Pull priors (parent)

Assemble the prior bundle described above. Keep it tight — sub-agents
also operate caveman; bloating their context defeats the purpose.

### 4. Spawn sub-agents in parallel (parent)

Use the Agent tool with `subagent_type=general-purpose` (or a more
specialized type if the question warrants it). Send both sub-agents
in a single tool-call batch so they run concurrently.

Prompt template per sub-agent (parent fills the angle-bracket
placeholders):

```
You are arguing <Side A | Side B> on the following contested
question:

<one-sentence question>

Your assigned stance: <stance summary>

Operate in caveman mode for all output: terse, no filler,
fragments OK, technical content exact. The auto-clarity exception
in caveman/SKILL.md still applies.

Priors (read these before arguing):
<excerpted CONTEXT.md terms>
<ADR titles + one-liners; load-bearing ADR bodies inline>
<kb_src rules in scope>
<integrations + license clauses if relevant>

Allowed helper skills: caveman, domain-model,
improve-codebase-architecture, cache-hygiene, <others>.

Produce, in caveman:

1. The strongest 3 arguments for your assigned side, each grounded
   in a specific prior, fact, or first-principles claim. No vibes.
2. The strongest 1 argument the other side will throw at you, and
   how you'd answer it.
3. Any factual question whose answer would change your conclusion;
   mark each with "ASK-PARENT:" prefix. Do not fabricate; ask.
4. Concrete acceptance test: under what observable condition would
   you concede this side is wrong?

Do NOT propose synthesis or compromise. The parent will synthesize.
Argue your side fully. If your side is genuinely indefensible against
the priors, say so explicitly and why.
```

### 5. Collect + parent resolves what it can

For every `ASK-PARENT:` question across both sub-agents:

- If the answer exists in `CONTEXT.md` / `docs/adr/` / `kb_src` /
  `AGENTS.md` / repo state → answer it from there.
- If the answer requires running a command (e.g., "how big is the
  toolchain after pruning?") → run it and answer.
- If the question is preference-shaped — taste, risk-appetite,
  strategic direction, business call — **escalate to user** with a
  one-sentence framing. Do not guess.

### 6. Round 2 if needed

If both sides have unresolved cruxes after their answers come back,
re-spawn both sub-agents with the new information appended to the
prior bundle. **Hard cap at two rounds.** A third round means the
question is malformed; reframe and restart, or route to `grill-me`
to interview the user instead.

### 7. Synthesize (parent)

Write the resolution. Possible shapes:

- **Side A wins outright.** State why; cite the deciding factor.
- **Side B wins outright.** Same.
- **Hybrid.** When both sides identified non-overlapping concerns
  the resolution must address; describe the synthesis explicitly,
  not as a hand-wave.
- **Defer.** When neither side can be picked without information
  the project does not yet have; capture what info would unblock
  the decision and stop. Do not write an ADR for "we couldn't
  decide" — write a `kb_src` rule that names the missing data.

### 8. Write artifacts

Always exactly one of:

| Outcome | ADR for accepted | ADR for rejected | New kb_src rule | New skill |
|---------|------------------|------------------|-----------------|-----------|
| Clean win, rejection non-obvious | yes | yes | maybe | no |
| Clean win, rejection self-evident | yes | no | no | no |
| Hybrid | yes (synthesis) | yes (each pure side) | maybe | no |
| Defer | no | no | yes (names the gap) | no |
| Recurrence detected (this class of question keeps coming up) | yes | depends | yes | maybe |

A "recurrence pattern" earns a new skill or kb_src rule when the
*shape* of the debate is reusable: similar parties, similar priors,
similar resolution mechanism. Most debates are one-shots; do not
manufacture a skill from one fight.

### 9. Commit

ADR(s) and any new skill / kb_src row land in the same commit as the
change they govern, per `git-style`. If the debate produced no
artifact (rare; usually means the gate-check should have failed),
explicitly say so and explain why.

## Escalation rules to the user

Escalate when the crux is:

- **Strategic direction** — "should the Template be public or
  private?" — operator-only call.
- **Risk appetite** — "are we OK with always-on paid infra for
  long-term agent autonomy, given cache-hygiene §1?"
- **Taste / identity** — "do we want to be 'the agentic Rails' or
  'one operator's plumbing'?"
- **Resource commitment** — anything that costs the user real time or
  money beyond what they've already authorized.

Do **not** escalate when the answer is:

- Already in an ADR / CONTEXT.md / kb_src / AGENTS.md → look it up.
- Discoverable from a single command → run it.
- A preference one of the sub-agents already supplied as a stated
  assumption — record the assumption in the ADR and proceed.

Each escalation to the user must be a single specific question with
the two defensible answers and the consequence of each. No menus, no
"thoughts?" prompts.

## Anti-patterns

- **Auto-firing.** Invoking on every choice. The four-condition gate
  is the whole game; if you skip the gate, you fail the skill.
- **Manufactured dissent.** A sub-agent generating plausible-sounding
  arguments without grounding in priors. Empty arguments must be
  flagged as "no defensible argument from priors" rather than
  fabricated.
- **Synthesis from sub-agents.** Sub-agents argue; the parent
  synthesizes. Letting a sub-agent propose the compromise corrupts
  the adversarial frame.
- **Crux-laundering escalation.** Bouncing a fact-lookup or
  command-runnable question to the user because it's faster.
  Disrespects the user's time and hollows the skill's authority.
- **ADR for trivia.** If the resolution is reversible or self-
  evident in retrospect, do not write an ADR. Use a kb_src row or
  nothing.
- **Round 3.** Hitting round 3 means the question is wrong-shaped.
  Reframe.
- **Sub-agents not in caveman.** Doubles token spend, halves
  signal density. The system prompt must enforce caveman every time.

## Read first

- `.agents/skills/decision-record/SKILL.md` — the ADR gating bar.
- `.agents/skills/domain-model/SKILL.md` — for ADR-applied
  resolution when the question is already settled.
- `.agents/skills/grill-me/SKILL.md` — when the right answer is
  more interview than debate.
- `.agents/skills/ideate/SKILL.md` — when the question is "what are
  the options?" rather than "which of these two is right?"
- `.agents/skills/caveman/SKILL.md` — communication mode for the
  whole orchestration.
- `CONTEXT.md` and `docs/adr/index.md` — every debate's priors.
