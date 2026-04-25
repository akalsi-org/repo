# AGENTS.md

## 2.1 Agent Skills

| Skill | Engage when | Definition |
|-------|-------------|------------|

Routes, when present, live in `.agents/skills/index.md`.

## 3. Maintenance Contract

Agents working in this repository must preserve the template as a reusable
bootstrap substrate. Keep repository-specific behavior configured through
`.agents/repo.json`, update `AGENTS.md` when commands, agent assets, hooks, or
subsystem descriptor rules change, and run `./repo.sh agent-check --stale-only`
plus `git diff --check` before handing work back.

## 5. Repo Layout

- `repo.sh` is the environment launcher.
- `.agents/repo.json` is the repository contract consumed by tools.
- `.agents/skills/`, `.agents/reviews/`, and `.agents/kb-src/` hold agent assets.
- `tools/` holds commands exposed through `repo.sh`.
- `tools/git-hooks/pre-commit` is the managed pre-commit hook source.

## 8. Commands

| Command | Mode | Purpose |
|---------|------|---------|
| `agent` | Python | Query and maintain the repository agent knowledge base. |
| `agent-check` | Python | Check skill routing, docs references, and configured command inventory. |
| `setup` | Python | Install or report local managed repository hooks. |
| `source-mirror` | Python | List or upload configured byte-identical upstream source mirrors. |

## 15. Subsystems

| Subsystem | Layer | Purpose | Detail |
|-----------|-------|---------|--------|
