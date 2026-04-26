# Declared bootstrap tool dependencies

Bootstrap tool ordering is declared by each per-tool spec instead of
hard-coded in `repo.sh`. A spec may set `TOOL_DEPS=(...)` with other
bootstrap tool names. `repo.sh` queries every spec with
`BOOTSTRAP_PLAN_ONLY=1`, validates unknown dependencies, self
dependencies, and cycles, then builds dependency-ready batches.

Today those batches are consumed serially. The batch shape is the
durable interface: every tool in a batch is ready to run after all
previous batches finish, so a future queue can hand the next `N`
ready tasks to workers without changing the spec format.

This keeps local bootstrap agility incremental. Adding a stage-0 tool,
making Python depend on bwrap, or introducing a compiler/runtime stack
does not require maintaining a second ordering list in the launcher.
The source of truth stays with the tool that knows its own needs.

## Considered options

- Keep a hard-coded priority list in `repo.sh`. Rejected because it
  makes every new dependency a launcher edit and hides the reason for
  ordering away from the owning spec.
- Infer dependencies from helper use or paths. Rejected because the
  repo should not guess internal bootstrap machinery; missing
  declarations should fail directly.
- Execute ready batches in parallel immediately. Deferred because the
  queue boundary is now explicit, while serial execution keeps first
  implementation simple and easier to debug.
