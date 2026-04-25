# AGENTS.md

Repo-truth contract for agents working in this template (and the
products forked from it). Humans should read `README.md`; both
documents describe the same facts in different framings.

## 1. Default communication style

All agents operate in **caveman mode** by default in this repository:
terse, no filler, articles dropped, fragments OK, technical content
exact. See `.agents/skills/caveman/SKILL.md`. Override per-session by
saying "stop caveman" or "normal mode."

The auto-clarity exception still applies — drop caveman temporarily
for security warnings, irreversible-action confirmations, and
multi-step sequences where fragment order risks misread. Resume
caveman after.

## 2.1 Skills

Procedures live in `.agents/skills/<name>/SKILL.md`. Routing by path
pattern lives in `.agents/skills/index.md`. Skill folder names use
hyphens; everything else uses underscores (see §6 Naming).

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `caveman` | Always active by default; user toggles off explicitly. | `.agents/skills/caveman/SKILL.md` |
| `doc-sync` | Changing AGENTS.md, README, CONTEXT.md, docs/adr/, .agents/skills/index.md, .agents/kb_src/, layout, command docs. | `.agents/skills/doc-sync/SKILL.md` |
| `git-style` | Any git operation on behalf of the user — commits, branches, remotes, worktrees. | `.agents/skills/git-style/SKILL.md` |
| `knowledge-management` | Adding, querying, pruning entries in `.agents/kb_src/`. | `.agents/skills/knowledge-management/SKILL.md` |
| `tdd` | Building features or fixing bugs with tests-first; mention of "red-green-refactor". | `.agents/skills/tdd/SKILL.md` |
| `simplify` | After a feature lands, before a PR, or "tighten / clean up / simplify". | `.agents/skills/simplify/SKILL.md` |
| `design-an-interface` | Designing a new module API or comparing module shapes ("design it twice"). | `.agents/skills/design-an-interface/SKILL.md` |
| `domain-model` | Stress-testing a plan against `CONTEXT.md` and existing ADRs. | `.agents/skills/domain-model/SKILL.md` |
| `improve-codebase-architecture` | Finding deepening opportunities, consolidating shallow modules. | `.agents/skills/improve-codebase-architecture/SKILL.md` |
| `decision-record` | A hard-to-reverse, surprising, trade-off-driven call has been made. | `.agents/skills/decision-record/SKILL.md` |
| `grill-me` | Stress-testing a plan via relentless interview. | `.agents/skills/grill-me/SKILL.md` |
| `ideate` | Generating a horizon-spanning idea portfolio (short / medium / long / visionary) with 1st-/2nd-/3rd-order effect classification. | `.agents/skills/ideate/SKILL.md` |
| `triage-issue` | A bug needs investigation + a TDD fix plan filed as an issue. | `.agents/skills/triage-issue/SKILL.md` |
| `to-issues` | Breaking a plan into independently-grabbable GitHub issues. | `.agents/skills/to-issues/SKILL.md` |
| `request-refactor-plan` | Detailed refactor plan + tiny commits filed as a GitHub issue. | `.agents/skills/request-refactor-plan/SKILL.md` |
| `bootstrap-toolchain` | Adding/upgrading/removing pinned tools, editing fetcher helpers. | `.agents/skills/bootstrap-toolchain/SKILL.md` |
| `cache-hygiene` | Changing CI cache config, fetch helpers, per-tool prune rules, source-mirror or bootstrap-artifact behavior. | `.agents/skills/cache-hygiene/SKILL.md` |
| `bootstrap-product` | Forking the template into a new named product. | `.agents/skills/bootstrap-product/SKILL.md` |
| `initialize` | User just cloned; helping run or extend `tools/initialize`. | `.agents/skills/initialize/SKILL.md` |

## 3. Maintenance contract

Agents working in this repository must preserve the template as a
reusable bootstrap substrate.

- Repository-specific behavior is configured through
  `.agents/repo.json`, never hard-coded into core scripts or skills.
- `AGENTS.md` is updated when commands, agent assets, hooks,
  integrations, or descriptor rules change.
- Run `./repo.sh agent_check --stale-only` and `git diff --check`
  before handing work back.

Cache and mirror paths are accelerators only. A miss from `.local/`,
the source mirror, or a bootstrap artifact must not be fatal during
normal bootstrap; the source path remains canonical. Upload/publish
commands may fail on missing or invalid configured inputs because
those commands are explicitly maintaining the cache.

Commands that can perform an expensive build or bootstrap step should
expose a `--no-build` or equivalent reuse flag when they are also
useful after an explicit prior build. CI prefers an explicit build
step followed by reuse-mode test, package, benchmark, or system-test
steps so failures identify the stage that broke.

## 5. Layout

| Path | Role |
|------|------|
| `repo.sh` | Environment launcher. Exports `REPO_ROOT`, `REPO_LOCAL`, `REPO_TOOLCHAIN`, `REPO_ARCH`, `REPO_SHELL`. |
| `AGENTS.md` | This file. Agent-facing repo contract. |
| `README.md` | Human-facing entry point. Same facts, different framing. |
| `CONTEXT.md` | Domain language for the product. |
| `docs/adr/NNNN_*.md` | Architectural decision records. Sequential numbering, underscore separator. |
| `LICENSE` | PolyForm Strict 1.0.0 by default. |
| `.editorconfig` | Editor baseline; keep when adapting the template. |
| `.agents/repo.json` | Per-product knobs (name, owner, license year, tooling). |
| `.agents/skills/<name>/` | Skill bodies. Hyphenated folder names. |
| `.agents/skills/index.md` | Path-pattern → skill routing table. |
| `.agents/kb_src/core.jsonl` | Durable agent KB facts. |
| `.agents/kb_src/tables/<name>.jsonl` | Larger structured fact collections (when needed). |
| `.agents/reviews/<skill>.md` | Optional skill-specific review notes. |
| `bootstrap/fetch_binary.sh` | Generic helper: pinned binary tarball → `.local/toolchain/$REPO_ARCH`. |
| `bootstrap/fetch_source.sh` | Generic helper: pinned source build. |
| `bootstrap/tools/<tool>.sh` | Per-tool spec sourcing one helper. |
| `bootstrap/vars/local_cache_key.sh` | CI cache-key sentinel. Bump `cache_epoch` to invalidate helpers. |
| `tools/` | Every command exposed via `./repo.sh`. |
| `tools/git_hooks/pre-commit` | Managed pre-commit hook source. |
| `.local/toolchain/$REPO_ARCH/` | Toolchain install prefix. Cached, not committed. |
| `.local/stamps/` | Tool install stamps + `initialized` marker. |
| `.claude/skills`, `.codex/skills`, `.github/instructions/skills` | Symlinks to `.agents/skills/`. Multi-agent surface. |

## 8. Commands

| Command | Mode | Purpose |
|---------|------|---------|
| `initialize` | Python | Idempotent post-clone setup: render LICENSE/README, seed CONTEXT.md + docs/adr/, run setup + bootstrap + agent_check, stamp completion. |
| `agent` | Python | Query and maintain the repository agent knowledge base. |
| `agent_check` | Python | Validate skill routing, doc references, and configured command inventory. Rejects `_` in skill folder names. |
| `setup` | Python | Install / status / uninstall managed git hooks and configured VSCode plugins. |
| `source_mirror` | Python | List or upload configured byte-identical upstream source mirrors. |

## 6. Naming

- Files, directories, config keys, Python modules, generated
  identifiers, cache keys, and internal command names: **`_`**.
- CLI flags: **`-` / `--`** (conventional).
- Skill folder names under `.agents/skills/`: **`-`** only — external
  agent runtime discovery convention. `agent_check` rejects `_`
  here.
- Do not add hyphenated command aliases in this template; commands
  are named once with underscores.

## 7. Integrations

| Service | Default credential source | Notes |
|---------|---------------------------|-------|
| GitHub | `GITHUB_TOKEN` env, else `~/github.token` (mode `0600`). | Used by `gh` and any tool calling the GitHub API. Permissions on the file should be `0600`. |

When adding a new third-party integration, document it in this table
and in `README.md` Integrations. Read credentials from
`~/<service>.token` or an environment variable; never commit them to
the repo and never log them.

## 14. CI

CI restores `.local/toolchain/` plus `.local/stamps/` with
`actions/cache/restore`, runs the bootstrap and agent checks through
`./repo.sh`, and saves those bootstrap paths only from non-PR runs on
cache misses. Cache keys are scoped by architecture and by
`bootstrap/vars/local_cache_key.sh`, `.agents/repo.json`, and
`bootstrap/tools/*.sh`.

`cache_warm.yml` periodically restores the same cache keys to reset
GitHub's LRU timer. Restore misses are acceptable and must not fail
the workflow.

## 15. Subsystems

| Subsystem | Layer | Purpose | Detail |
|-----------|-------|---------|--------|

(The template ships with no subsystems. Products add rows here as
they grow.)
