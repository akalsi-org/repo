# repo

The agentic bootstrap template itself. This context is small on
purpose — products forked from the template will replace this file
with their own domain language.

## Language

**Template**:
This repository in its undifferentiated form. A user does not run a
template directly; they fork it and run `initialize` to produce a
**Product**.
_Avoid_: starter, scaffold, boilerplate.

**Product**:
A repository derived from the **Template** by `./repo.sh initialize`.
A Product has a name, an owner, a license year, and its own
`CONTEXT.md`, `docs/adr/`, and `README.md`.
_Avoid_: app, project, repo (overloaded).

**Skill**:
A directory under `.agents/skills/<name>/` containing at minimum a
`SKILL.md` describing when an agent should engage and what procedure
to follow. Folder name is hyphenated.

**Agent**:
A model-driven assistant operating in this repository (Claude, Codex,
Copilot, etc.). Agents read `AGENTS.md`, the active **Skills**, and
the **KB**.

**KB** (Knowledge Base):
Durable facts in `.agents/kb_src/**/*.jsonl` consumed by the `agent`
command. Cache and runtime tables are derived from the KB and not
hand-edited.

**Worktree**:
A git worktree of the bare repo. The Template assumes a
`.bare/ + worktree/` layout for AI-friendly parallelism, with
`.local/` shared across worktrees.

**Toolchain**:
Pinned third-party tools fetched into `.local/toolchain/$REPO_ARCH/`
by per-tool specs under `bootstrap/tools/`. Never the system package
manager.

**Subsystem**:
A coherent slice of the Product with its own `AGENTS.md` row and
optionally its own nested `AGENTS.md`. The Template ships with no
subsystems.

## Relationships

- A **Template** produces one or more **Products**.
- A **Product** has many **Skills** (mostly inherited from the
  Template).
- An **Agent** consumes **Skills** + the **KB** + `AGENTS.md`.
- A **Toolchain** is shared by all **Worktrees** of a **Product**.

## Flagged ambiguities

- "skill" was used to mean both an agent-facing markdown procedure and
  the harness's runtime concept of a "skill" — both refer to the same
  thing here, addressed by hyphenated folder names so external
  discovery works.
