---
name: bootstrap-product
description: Use when forking this template into a new product. Sets the product name, owner, license year, and seeds CONTEXT.md / docs/adr/ / README from the template stubs. Pairs with the `initialize` skill which is the runnable entry point.
---

# bootstrap-product

Convert a fresh template clone into a named product ready to build on.
Most users invoke this through `./repo.sh initialize` (see the
`initialize` skill); this skill documents what that command performs
and how to extend it per-product.

## Prereqs

- Clone or worktree of the template, not the template repo itself.
- `~/github.token` populated if the product will publish to GitHub
  (see `AGENTS.md` Integrations).

## What `initialize` performs

1. **Read or prompt for product knobs.** Either flags
   (`--name`, `--owner`, `--license-year`, `--description`) or
   interactive prompts. Persists answers in `.agents/repo.json`.

2. **Render LICENSE** by substituting `{{OWNER}}` and `{{YEAR}}` in
   the PolyForm Strict 1.0.0 stub.

3. **Render README** by substituting `{{PRODUCT_NAME}}`,
   `{{DESCRIPTION}}`, and integration placeholders.

4. **Seed `CONTEXT.md`** with the product name as the context name,
   an empty Language section, and a placeholder dialogue.

5. **Create `docs/adr/0001_initial.md`** recording the choice to
   adopt this template + PolyForm Strict.

6. **Run `./repo.sh setup`** to install the pre-commit hook and any
   configured VSCode extensions.

7. **Run `./repo.sh true`** to fetch any pinned tools.

8. **Run `./repo.sh agent_check --stale-only`** as a smoke test.

9. **Print next steps** — what verbs the user can now run, where
   `.agents/repo.json` lives if they want to change anything, and
   the link to `AGENTS.md` Integrations.

## Idempotency

- A subsequent run detects `.local/stamps/initialized` and prints
  the current state without re-prompting. `--force` re-runs everything.
- Editing `.agents/repo.json` by hand is supported; re-running
  `initialize` after a hand edit reconciles LICENSE/README from the
  new values.
- ADR `0001_initial.md` is created only if absent.

## Per-product extension

Products that need more than the defaults (e.g., a different deploy
target, a registry, custom toolchain) should:

- Add per-tool fetchers under `bootstrap/tools/<tool>.sh`
  (see `bootstrap-toolchain`).
- Add subsystem rows to AGENTS.md §Subsystems.
- Add ADRs for each load-bearing choice (`decision-record`).
- Extend `tools/initialize` only if the new step is genuinely
  product-agnostic; otherwise add a separate command.
