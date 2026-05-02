# repo

An agentic bootstrap template for sellable software products. Clone
it, run `./repo.sh initialize`, and a fork starts with skills,
documentation, toolchain fetching, and a license configured.

The template is opinionated about three things:

1. **AI affordance is product affordance.** Every convention exists
   to make agents (Claude, Codex, Copilot) and humans equally
   productive in the same repo.
2. **Cheap to build, maintain, and operate.** No SaaS dependencies,
   no idle costs, no proprietary tooling required to bootstrap.
3. **Caches and accelerators are never load-bearing.** A miss must
   not break a fresh clone.

## Quick start

```sh
git clone <this-template> myproduct
cd myproduct
./repo.sh initialize     # idempotent; sets product name, owner, license year
./repo.sh                # opens a shell with REPO_* env vars set
```

## Verb surface

Every command runs through `./repo.sh <verb> [args]`:

| Verb | Purpose |
|------|---------|
| `initialize` | Idempotent post-clone setup: renders LICENSE/README, seeds CONTEXT.md + docs/adr/ + target ledger + starter backlog, runs setup + bootstrap + agent_check. |
| `setup` | Install / status / uninstall managed git hooks and configured VSCode plugins. |
| `agent` | Query and maintain the repository agent knowledge base. |
| `agent_check` | Validate skill routing, doc references, and Facet-backed command inventory. |
| `ideas` | Manage idea inventory, scoring, readiness gates, learning-ledger queries, stale idea reports, and evidence-backed next-bet activation. |
| `source_mirror` | List or upload configured byte-identical upstream source mirrors. |
| `system_test` | Run repo-level clustered plain and bwrap backend smoke tests from the scenario manifest. |
| `infra` | Multi-provider VM fabric verb: adopt, status, wg-up, deploy. Placeholder; subcommands land with issue #3 (see ADR-0014). |

`./repo.sh` with no args opens a subshell with `REPO_ROOT`,
`REPO_LOCAL`, `REPO_TOOLCHAIN`, `REPO_ARCH`, `REPO_SHELL` exported.

## Layout

| Path | What lives there |
|------|------------------|
| `AGENTS.md` | Agent-facing repo contract. Skill table, command table, integrations, CI summary, subsystems. |
| `CONTEXT.md` | Domain language for the product. |
| `docs/adr/` | Numbered architectural decision records (`NNNN_slug.md`). |
| `.agents/skills/` | Per-skill `<name>/SKILL.md` (hyphenated names; never underscored). |
| `.agents/facet/` | Declarative Facet manifests for repo-level AI capabilities; presence means enabled. |
| `.agents/facet/maintenance/` | Scheduled repo upkeep ownership, including CI cache warming. |
| `.agents/facet/system_test/scenarios.json` | System-test scenario manifest: default cluster size, shared service port, host port base, and enabled backend checks. |
| `.agents/ideas/ideas.jsonl` | Canonical idea inventory and backlog gate input, including safe-parallel worktree metadata. |
| `.agents/targets/targets.jsonl` | Canonical target ledger: durable repo goals referenced by idea rows. |
| `.agents/kb_src/core.jsonl` | Durable agent KB facts. |
| `.agents/repo.json` | Per-product knobs and Facet configuration. |
| `bootstrap/fetch_binary.sh` | Generic helper: pinned binary tarball → `.local/toolchain/$ARCH`. |
| `bootstrap/fetch_source.sh` | Generic helper: pinned source build. |
| `bootstrap/tools/<tool>.sh` | Per-tool spec sourcing one helper; optional `TOOL_DEPS` declarations let `repo.sh` topologically batch bootstrap work. `python.sh` pins repo Python and `bwrap.sh` pins the sandbox backend. |
| `bootstrap/vars/local_cache_key.sh` | CI cache-key sentinel. |
| `tools/` | Every command exposed via `./repo.sh`. |
| `.local/` | Toolchain cache, stamps, build state. Never committed. |
| `.agents/skills/core-infra-lead/` | Agent role for the multi-provider VM fabric (ADR-0014). |
| `.agents/facet/core_infra/` | Facet manifest for the fabric: owned paths, considerations, doc projections. |
| `bootstrap/providers/<name>.sh` | Per-provider provisioning plugin (`create_vm`/`destroy_vm`/`list_vms`/`region_list`/`size_list`). Lands with later issues; Hetzner first. |
| `tools/infra/` | `infra` verb implementation. Lands with issue #3. |

## Integrations

| Service | Default credential source | Notes |
|---------|---------------------------|-------|
| GitHub | `GITHUB_TOKEN` env, else `~/github.token` (mode `0600`) | Used by `gh` and any tool calling the GitHub API. |
| VM provider (Hetzner, etc.) | `~/<provider>.token` (mode `0600`) | Read by `bootstrap/providers/<name>.sh` for `create_vm` / `destroy_vm` / `list_vms`. Tokens stay on the operator's machine; never pushed to fabric hosts. See ADR-0014. |

When you add a new third-party integration, document it in this
table and in `AGENTS.md` Integrations. Never commit credentials.

### GitHub identity is discovered at runtime, never hard-coded

The fabric and downstream automation pull three things from GitHub:
SSH `authorized_keys` (`https://github.com/<login>.keys`), the org for
self-hosted Actions runners, and the `ghcr.io` namespace for
systemd-deploy artifacts. In all three cases `<login>` and `<org>` are
resolved at runtime via `GET /user` against `~/github.token`.
**No tracked file in this repo may contain a concrete GitHub login or
org as a literal string.** Operators can override per host; the
default is always discovered. See ADR-0014.

## Agent compatibility

Skills under `.agents/skills/` are surfaced to multiple agents via
symlinks:

- `.claude/skills` → `.agents/skills`
- `.codex/skills` → `.agents/skills`
- `.github/instructions/skills` → `.agents/skills`

All three agents read the same skill bodies. Per-agent settings
remain agent-local (e.g. `.claude/settings.local.json`).

This template defaults to **strict caveman mode** for all agent
communication. Agents should keep caveman wording in questions,
progress updates, plans, designs, explanations, and final handoff text
unless the user explicitly says "stop caveman" or "normal mode."
Caveman here means terse, no filler, fragments OK, technical content
exact.

## Naming rules

- Files, directories, config keys, Python modules, generated
  identifiers, cache keys, and internal command names: `_` (underscore).
- CLI flags: `-` / `--` (conventional).
- Skill folder names under `.agents/skills/`: `-` (hyphen) only —
  external skill discovery convention. `agent_check` rejects `_` here.

## License

PolyForm Strict License 1.0.0 — see [LICENSE](./LICENSE). Commercial
use requires a separate agreement with the licensor.
