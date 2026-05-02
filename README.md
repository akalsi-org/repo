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
| `pyext-build` | Compile one typed Python module with mypyc into a musl CPython extension under `build/mypyc/$REPO_ARCH/`. |
| `ideas` | Manage idea inventory, scoring, readiness gates, learning-ledger queries, stale idea reports, and evidence-backed next-bet activation. |
| `source_mirror` | List or upload configured byte-identical upstream source mirrors. |
| `system_test` | Run repo-level clustered plain and bwrap backend smoke tests from the scenario manifest. |
| `infra` | Multi-provider VM fabric verb. `adopt` brings an SSH-reachable host onto the inventory with WireGuard probe + tuned sysctls + GH-keys-sync; `status` lists adopted hosts and last-known reachability; `wg-up <ssh_target>` generates the per-cluster WG keypair on the host, renders `/etc/wireguard/wg-c<cluster>.conf` from the local peer table, installs the `wg-overlay@<cluster>.service` unit, and enables it for reboot survival; `wg-peer-add <a> <b>` registers two adopted hosts as peers symmetrically and re-renders both configs; `vxlan-up <ssh_target>` stacks the per-cluster VXLAN overlay on top of WG (one VNI per cluster, head-end-replicated FDB for broadcast, inner MTU 1370 by default), installs the `vxlan-overlay@<cluster>.service` unit, and renders the `/etc/hosts` block; `hosts-render <ssh_target>` re-renders the `/etc/hosts` block from the current peer table without touching VXLAN; `provision-hetzner` creates Hetzner Cloud nodes with CAX ARM64 default; `decommission <provider> <vm_id>` destroys supported provider VMs and removes inventory. `deploy` lands with later issues. See ADR-0014. |
| `personality` | Multi-CLI persistent personalities. `list` shows the roster + last_active; `init <name> --cli claude\|codex\|copilot` scaffolds a definition; `as-root <name>` opens an interactive persistent session via native CLI resume (or fresh seed); `ask <name> "<prompt>"` runs a one-shot non-interactive call (native resume preferred, transcript replay fallback) and prints only the reply on stdout; `clear <name>` wipes `.local/personalities/<name>/` while preserving the definition. Definitions live under `.agents/personalities/<name>/personality.md`; defaults at `.agents/personalities/_defaults.yaml`. |

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
| `tests/fixtures/pyext_smoke/` | Smoke fixture for mypyc-built Python extension import checks. |
| `.local/` | Toolchain cache, stamps, build state. Never committed. |
| `.agents/skills/core-infra-lead/` | Agent role for the multi-provider VM fabric (ADR-0014). |
| `.agents/facet/core_infra/` | Facet manifest for the fabric: owned paths, considerations, doc projections. |
| `bootstrap/providers/_template.sh` | Abstract provider shape: documents the five required functions plus credential-path convention. Not loaded at runtime. |
| `bootstrap/providers/contabo.sh` | Contabo provider — label-only stub in this slice (adopt-only). API impl is deferred. |
<<<<<<< HEAD
| `bootstrap/providers/<name>.sh` | Per-provider provisioning plugin (`create_vm`/`destroy_vm`/`list_vms`/`region_list`/`size_list`). Hetzner uses CAX ARM64 by default; x86 capacity is Contabo BYO via `adopt`. |
| `tools/infra` | `infra` verb dispatcher (Python). Subcommands `adopt`, `status`, `wg-up`, `wg-peer-add`, `vxlan-up`, `hosts-render`, `provision-hetzner`, `decommission`. |
| `tools/infra_pkg/` | Implementation modules + systemd unit templates (`units/gh-keys-sync.{service,timer}.in`, `units/wg-overlay@.service.in`, `units/vxlan-overlay@.service.in`) used by `infra adopt`, `infra wg-up`, and `infra vxlan-up`. The WG and VXLAN templates are the systemd templated form (`@.service`) — `${CLUSTER_ID}` and (for VXLAN) `${EXECSTART_BLOCK}` are substituted at install time, `%i` carries the cluster id at runtime. |
| `tools/infra_pkg/adopt.sh` | Bash shim that delegates to `tools/infra adopt ...` for operators who prefer the explicit script path. |
| `.agents/personalities/` | Committed personality definitions (`<name>/personality.md`) + `_defaults.yaml` (per-CLI model + effort defaults). Reviewed like skills. |
| `.agents/skills/personality/` | Skill body for the multi-CLI personalities verb (issue #14). Routable from Claude/Codex/Copilot via the existing skill-symlink convention. |
| `.agents/facet/personality/` | Facet manifest for the personalities slice: owned paths, the `personality` command, and the `personality_tests` closeout check. |
| `tools/personality` | `personality` verb dispatcher (Python). Subcommands `list`, `init`, `as-root`, `ask`, `clear`. |
| `tools/personality_pkg/` | Implementation modules: `definitions.py` (front-matter + defaults parser), `state.py` (lock + state layout under `.local/personalities/`), `transcript.py` (append-only JSONL + replay-prompt builder), per-CLI adapters (`claude_adapter.py`, `codex_adapter.py`, `copilot_adapter.py`), `runner.py` (subprocess + exec wrapper), and `commands/` (one file per subcommand). |
| `.local/personalities/<name>/` | Per-machine session state: `session_id`, `session_meta.yaml`, `transcript.jsonl`, `lock`, `last_invocation.json`, `last_stdout.txt`, `last_stderr.txt`, `replay_prompt.md`. Gitignored under `.local/`. |

Fast-Python hot paths use pinned `mypy[mypyc]` with the Zig musl
toolchain. Built `.so` modules ship with products; mypyc remains a
dev/CI tool.
`bootstrap/tools/librt.sh` source-builds mypyc's native runtime helper
with the same Zig musl ABI.

## Integrations

| Service | Default credential source | Notes |
|---------|---------------------------|-------|
| GitHub | `GITHUB_TOKEN` env, else `~/github.token` (mode `0600`) | Used by `gh` and any tool calling the GitHub API. |
| Hetzner Cloud | `HETZNER_TOKEN` env, else `~/hetzner.token` (mode `0600`) | API provisioning provider. ARM64 CAX is default instance family; x86 routes through Contabo BYO via `adopt` (#3), though CX/CCX list support exists for explicit API use. Token stays on operator machine; never pushed to fabric hosts. |
| VM provider (Contabo, etc.) | `~/<provider>.token` (mode `0600`) | Provider convention for future APIs. Contabo is adopt-only in this template slice; power off through Contabo UI. See ADR-0014. |
| GH-keys-sync (per-host systemd timer) | `https://github.com/<login>.keys` over plain HTTPS | Installed by `infra adopt`. `<login>` is **runtime-discovered** by `GET /user` against `~/github.token` (or `GITHUB_TOKEN`); operator can override with `--ssh-keys-github=<other>` or disable via `--ssh-keys=<path>`. **No concrete login is hard-coded anywhere in this repo.** Default refresh interval 15 minutes. Unit template at `tools/infra_pkg/units/gh-keys-sync.service.in`. |

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
