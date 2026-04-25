---
name: initialize
description: Use when a user has just cloned the template (or run `./repo.sh initialize`) and needs help completing setup, recovering from a partial init, or extending the initializer.
---

# initialize

`tools/initialize` is the post-clone entry point. It is **idempotent**:
running it twice does no harm; running it after a partial failure
picks up where the previous run stopped.

## What it does

See `bootstrap-product` for the full sequence. In brief:

1. Resolve product knobs from flags / `.agents/repo.json` / prompts.
2. Render `LICENSE` (PolyForm Strict 1.0.0) and `README.md` from
   stubs.
3. Seed `CONTEXT.md` and `docs/adr/0001_initial.md` if missing.
4. Run `./repo.sh setup` (hooks, VSCode plugins).
5. Run `./repo.sh true` (toolchain fetch).
6. Run `./repo.sh agent_check --stale-only`.
7. Stamp `.local/stamps/initialized` and print next steps.

## Flags

```
./repo.sh initialize [--name NAME] [--owner OWNER] [--license-year YEAR]
                      [--description TEXT] [--force] [--non-interactive]
```

- `--force` re-runs all steps even if the stamp exists.
- `--non-interactive` fails if any required knob is missing rather
  than prompting.

## When to use this skill

- User asks "how do I set this up after cloning?"
- A previous `initialize` run failed; you need to diagnose where.
- User wants to add a new step to the initializer.

## Diagnosing a partial init

- `.local/stamps/initialized` present → previous run completed.
  Anything still wrong is post-init drift; do not re-run `initialize`,
  fix the specific surface.
- `.local/stamps/initialized` absent + `LICENSE` present + populated
  `.agents/repo.json` → previous run got past rendering; failure was
  in `setup` or `true`. Re-running is safe.
- `.agents/repo.json` empty → previous run failed before persisting
  knobs. Re-run.

## Extending the initializer

- Keep new steps **idempotent** — re-runnable without side effects.
- Keep new steps **product-agnostic** — anything product-specific
  belongs in a separate command, not in `initialize`.
- Persist any new knob in `.agents/repo.json` so re-runs are
  reproducible.
- Update `bootstrap-product` SKILL.md to mention the new step.

## Read first

- `tools/initialize` (the script).
- `.agents/repo.json` for current knob shape.
- `bootstrap-product/SKILL.md` for the canonical sequence.
- `AGENTS.md` Integrations for credentials the user must supply.
