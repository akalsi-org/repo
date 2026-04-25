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
| `initialize` | Idempotent post-clone setup: renders LICENSE/README, seeds CONTEXT.md + docs/adr/, runs setup + bootstrap + agent_check. |
| `setup` | Install / status / uninstall managed git hooks and configured VSCode plugins. |
| `agent` | Query and maintain the repository agent knowledge base. |
| `agent_check` | Validate skill routing, doc references, and command inventory. |
| `source_mirror` | List or upload configured byte-identical upstream source mirrors. |

`./repo.sh` with no args opens a subshell with `REPO_ROOT`,
`REPO_LOCAL`, `REPO_TOOLCHAIN`, `REPO_ARCH`, `REPO_SHELL` exported.

## Layout

| Path | What lives there |
|------|------------------|
| `AGENTS.md` | Agent-facing repo contract. Skill table, command table, integrations, CI summary, subsystems. |
| `CONTEXT.md` | Domain language for the product. |
| `docs/adr/` | Numbered architectural decision records (`NNNN_slug.md`). |
| `.agents/skills/` | Per-skill `<name>/SKILL.md` (hyphenated names; never underscored). |
| `.agents/kb_src/core.jsonl` | Durable agent KB facts. |
| `.agents/repo.json` | Per-product knobs (name, owner, license year, configured tooling). |
| `bootstrap/fetch_binary.sh` | Generic helper: pinned binary tarball → `.local/toolchain/$ARCH`. |
| `bootstrap/fetch_source.sh` | Generic helper: pinned source build. |
| `bootstrap/tools/<tool>.sh` | Per-tool spec sourcing one of the helpers. |
| `bootstrap/vars/local_cache_key.sh` | CI cache-key sentinel. |
| `tools/` | Every command exposed via `./repo.sh`. |
| `.local/` | Toolchain cache, stamps, build state. Never committed. |

## Integrations

| Service | Default credential source | Notes |
|---------|---------------------------|-------|
| GitHub | `GITHUB_TOKEN` env, else `~/github.token` (mode `0600`) | Used by `gh` and any tool calling the GitHub API. |

When you add a new third-party integration, document it in this
table and in `AGENTS.md` Integrations. Never commit credentials.

## Agent compatibility

Skills under `.agents/skills/` are surfaced to multiple agents via
symlinks:

- `.claude/skills` → `.agents/skills`
- `.codex/skills` → `.agents/skills`
- `.github/instructions/skills` → `.agents/skills`

All three agents read the same skill bodies. Per-agent settings
remain agent-local (e.g. `.claude/settings.local.json`).

This template defaults to **caveman mode** for all agent
communication — terse, no filler, technical content exact. Override
per-session by saying "stop caveman" or "normal mode."

## Naming rules

- Files, directories, config keys, Python modules, generated
  identifiers, cache keys, and internal command names: `_` (underscore).
- CLI flags: `-` / `--` (conventional).
- Skill folder names under `.agents/skills/`: `-` (hyphen) only —
  external skill discovery convention. `agent_check` rejects `_` here.

## License

PolyForm Strict License 1.0.0 — see [LICENSE](./LICENSE). Commercial
use requires a separate agreement with the licensor.
