# AGENTS.md

Repo-truth contract for agents working in this template (and the
products forked from it). Humans should read `README.md`; both
documents describe the same facts in different framings.

## 1. Default communication style

All agent output in this repository must use **strict caveman mode**
unless the user explicitly says "stop caveman" or "normal mode." This
applies to questions, plans, progress updates, design notes,
explanations, and final handoff text. Caveman means terse, no filler,
articles dropped, fragments OK, technical content exact. "Caveman"
always means strict caveman; there is no soft caveman, light caveman,
or mostly-caveman mode. Do not drift into normal prose just because a
task is complex or the user writes in normal prose. See
`.agents/skills/caveman/SKILL.md`.

The auto-clarity exception is narrow: drop strict caveman temporarily
only for security warnings, irreversible-action confirmations, or
multi-step sequences where fragment order risks misread. Resume strict
caveman immediately after the risky passage.

## 2.1 Skills

Procedures live in `.agents/skills/<name>/SKILL.md`. Routing by path
pattern lives in `.agents/skills/index.md`. Skill folder names use
hyphens; everything else uses underscores (see §6 Naming).

All skills organized by lifecycle tier (see ADR-0011). Core tier is
always available; phase-specific tiers activate when repo enters those
phases. Template-admin tier is operator-only, infrequent.

### Tier 1: Core (every session)

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `caveman` | Always active by default; user toggles off explicitly. | `.agents/skills/caveman/SKILL.md` |
| `git-style` | Any git operation on behalf of the user — commits, branches, remotes, worktrees. | `.agents/skills/git-style/SKILL.md` |
| `decision-record` | A hard-to-reverse, surprising, trade-off-driven call has been made. | `.agents/skills/decision-record/SKILL.md` |
| `c-suite` | Running a virtual executive board meeting to balance ideas, backlog, vision, cost, Facets, and priorities; CEO decides. | `.agents/skills/c-suite/SKILL.md` |
| `tdd` | Building features or fixing bugs with tests-first; mention of "red-green-refactor". | `.agents/skills/tdd/SKILL.md` |
| `knowledge-management` | Adding, querying, pruning entries in `.agents/kb_src/`. | `.agents/skills/knowledge-management/SKILL.md` |

### Tier 2: Phase-Specific (activate per lifecycle phase)

**Design / Decision phase:**

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `ideate` | Generating a horizon-spanning idea portfolio (short / medium / long / visionary) with 1st-/2nd-/3rd-order effect classification. | `.agents/skills/ideate/SKILL.md` |
| `grill-me` | Stress-testing a plan via relentless interview. | `.agents/skills/grill-me/SKILL.md` |
| `design-an-interface` | Designing a new module API or comparing module shapes ("design it twice"). | `.agents/skills/design-an-interface/SKILL.md` |
| `improve-codebase-architecture` | Finding deepening opportunities, consolidating shallow modules. | `.agents/skills/improve-codebase-architecture/SKILL.md` |
| `domain-model` | Stress-testing a plan against `CONTEXT.md` and existing ADRs. | `.agents/skills/domain-model/SKILL.md` |
| `debate-and-decide` | A load-bearing question is genuinely contested, no ADR resolves it, and at least two defensible positions exist. Two sub-agents argue; parent escalates only preference-shaped cruxes to the user. | `.agents/skills/debate-and-decide/SKILL.md` |

**Bootstrap phase:**

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `bootstrap-toolchain` | Adding/upgrading/removing pinned tools, editing fetcher helpers. | `.agents/skills/bootstrap-toolchain/SKILL.md` |
| `cache-hygiene` | Changing CI cache config, fetch helpers, per-tool prune rules, source-mirror or bootstrap-artifact behavior. | `.agents/skills/cache-hygiene/SKILL.md` |
| `bootstrap-product` | Forking the template into a new named product. | `.agents/skills/bootstrap-product/SKILL.md` |
| `initialize` | User just cloned; helping run or extend `tools/initialize`. | `.agents/skills/initialize/SKILL.md` |

**Debug / Refactor phase:**

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `triage-issue` | A bug needs investigation + a TDD fix plan filed as an issue. | `.agents/skills/triage-issue/SKILL.md` |
| `request-refactor-plan` | Detailed refactor plan + tiny commits filed as a GitHub issue. | `.agents/skills/request-refactor-plan/SKILL.md` |
| `simplify` | After a feature lands, before a PR, or "tighten / clean up / simplify". | `.agents/skills/simplify/SKILL.md` |

**Landing phase:**

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `to-issues` | Breaking a plan into independently-grabbable GitHub issues. | `.agents/skills/to-issues/SKILL.md` |
| `doc-sync` | Changing AGENTS.md, README, CONTEXT.md, docs/adr/, .agents/skills/index.md, .agents/kb_src/, layout, command docs. | `.agents/skills/doc-sync/SKILL.md` |

**Infra / runtime phase:**

| Skill | Engage when | Definition |
|-------|-------------|------------|
| `core-infra-lead` | Standing up, adopting, or operating the multi-provider VM fabric (ADR-0014): WG underlay, VXLAN overlay, gossip discovery, `infra` verbs. | `.agents/skills/core-infra-lead/SKILL.md` |
| `personality` | Running or delegating to named repo personalities (CEO, CFO, CTO, etc.) across Claude Code, Codex CLI, and GitHub Copilot CLI; persistent role sessions; cross-agent delegation; clearing a personality session. | `.agents/skills/personality/SKILL.md` |

## 3. Maintenance contract

Agents working in this repository must preserve the template as a
reusable bootstrap substrate.

- Repository-specific behavior is configured through
  `.agents/repo.json` and declarative `.agents/facet/<name>/facet.json`
  manifests, never hard-coded into core scripts or skills.
- Internal repo machinery should use one explicit source of truth and
  fail loudly when it is missing. Do not add fallback sources unless
  the user explicitly asks for them. Fallbacks are reserved for
  released artifacts, production paths, credentials, and cache/mirror
  accelerators where graceful degradation is part of the contract.
- `AGENTS.md` is updated when commands, agent assets, hooks,
  integrations, or descriptor rules change.
- Run `./repo.sh agent_check --stale-only` and `git diff --check`
  before handing work back.
- **Skill gate maintenance (ADR-0011):** Each skill's gate condition
  must reference current `CONTEXT.md` terms + `docs/adr/` decisions.
  Gates older than 180 days trigger stale flags in `agent_check`. Quarterly
  audit synchronizes gates with live documentation. Tier 1 (Core) skills
  require active use every session; Tier 2 (Phase-Specific) activate when
  repo enters that lifecycle phase; Tier 3 (Template-Admin) are operator-
  only and infrequent. Do not prune tier 2 skills to reduce template
  complexity — products fork, inherit all skills, and activate selectively.
- **Governance pack v2 maintenance (ADR-0012):** Products forking the
  template inherit baseline governance.json per Facet (schema_version: "2").
  governance.json must reference current cost/team structure and decision
  authority. Quarterly review synchronizes governance policies with org
  changes (team splits, budget adjustments, approval chain updates).

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

## 4. Safe parallel work

Parallel execution uses git worktrees. Each executable backlog item
must declare `parallel_mode`, `worktree`, and `write_scope` in
`.agents/ideas/ideas.jsonl` before an agent starts work.

- `parallel_mode=safe`: may run beside other `safe` items when
  `write_scope` sets do not overlap.
- `parallel_mode=serial`: run alone or only after explicit CEO
  approval; broad docs, initialization, Facet-schema, and cross-cutting
  command changes usually fit here.
- `parallel_mode=blocked`: not executable until the blocker is cleared.
- `worktree=required`: create or use a separate worktree for the item.
- `worktree=recommended`: worktree preferred; same worktree acceptable
  only for tiny documentation-only edits.
- `worktree=optional`: safe in current tree when no other active work
  overlaps.

Agents must not run two backlog items in parallel when their
`write_scope` globs overlap, when either item is `serial`, or when one
item depends on the other. Shared `.local/` is allowed; source edits
remain isolated by worktree.

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
| `.agents/repo.json` | Per-product knobs and `facet_config` values. Facet presence, not this file, controls enablement. |
| `.agents/facet/<name>/facet.json` | Declarative Facet manifests for repo-level AI capabilities: owned paths, commands, checks, and doc projections. |
| `.agents/facet/<name>/governance.json` | Optional. Facet-scoped governance rules: budget, approver, escalation policy, decision RACI, risk bands (see ADR-0012). Governance pack v2 enables Products to declare per-Facet governance; inheritance and override supported. |
| `.agents/facet/root/facet.json` | Root Facet. Display name `/`; owns baseline template substrate and repo-level defaults. |
| `.agents/facet/system_test/scenarios.json` | System-test scenario manifest. Declares default cluster size and enabled backend checks. |
| `.agents/ideas/ideas.jsonl` | Canonical idea inventory and backlog gate input, including safe-parallel worktree metadata. |
| `.agents/targets/targets.jsonl` | Canonical target ledger. Durable repo goals referenced by idea rows. |
| `.agents/skills/<name>/` | Skill bodies. Hyphenated folder names. |
| `.agents/skills/index.md` | Path-pattern → skill routing table. |
| `.agents/kb_src/core.jsonl` | Durable agent KB facts. |
| `.agents/kb_src/tables/<name>.jsonl` | Larger structured fact collections (when needed). |
| `.agents/reviews/<skill>.md` | Optional skill-specific review notes. |
| `bootstrap/fetch_binary.sh` | Generic helper: pinned binary tarball → `.local/toolchain/$REPO_ARCH`. |
| `bootstrap/fetch_source.sh` | Generic helper: pinned source build. |
| `bootstrap/fetch_alpine_bwrap.sh` | Helper: pinned Alpine minirootfs + bubblewrap apk + libcap apk → bwrap shim. |
| `bootstrap/tools/<tool>.sh` | Per-tool spec sourcing one helper. Specs may declare `TOOL_DEPS`; `repo.sh` topologically batches them. `python.sh` pins the repo machinery interpreter. |
| `bootstrap/vars/local_cache_key.sh` | CI cache-key sentinel. Bump `cache_epoch` to invalidate helpers. |
| `tools/` | Every command exposed via `./repo.sh`. |
| `tests/fixtures/pyext_smoke/` | Smoke fixture for mypyc-built Python extension import checks. |
| `tools/git_hooks/pre-commit` | Managed pre-commit hook source. |
| `.local/toolchain/$REPO_ARCH/` | Toolchain install prefix, including pinned Python. Cached, not committed. |
| `.local/stamps/` | Tool install stamps + `initialized` marker. |
| `.claude/skills`, `.codex/skills`, `.github/instructions/skills` | Symlinks to `.agents/skills/`. Multi-agent surface. |
| `.agents/skills/core-infra-lead/` | Agent role for the multi-provider VM fabric (ADR-0014). Owns the `infra` verb surface. |
| `.agents/facet/core_infra/facet.json` | Facet manifest for the fabric: owned paths under `bootstrap/providers/**`, `tools/infra`, `tools/infra_pkg/**`, `tools/infra_tests/**`, plus the agent role and ADR-0014. |
| `bootstrap/providers/_template.sh` | Abstract provider shape: documents `create_vm`/`destroy_vm`/`list_vms`/`region_list`/`size_list` and the `~/<provider>.token` mode-0600 convention. Not loaded at runtime. |
| `bootstrap/providers/contabo.sh` | Contabo provider — label-only stub in this slice. API surface is deferred; adopt is the only path to a Contabo host today. |
| `bootstrap/providers/<name>.sh` | Per-provider provisioning plugin reading `~/<provider>.token`. Hetzner lands with later issues. |
| `tools/infra` | `infra` verb dispatcher (Python). Subcommands `adopt`, `status`, `wg-up`, `wg-peer-add`. `deploy`, `provision` land with later issues. |
| `tools/infra_pkg/` | Implementation modules (adopt orchestrator, lscpu/identity helpers, GH discovery, inventory, sysctl + tuned templates, WG keypair/config helpers in `wg.py` + `wg_cmd.py`, VXLAN overlay + /etc/hosts renderers in `vxlan.py` + `vxlan_cmd.py`) and systemd unit templates under `units/`, including `units/wg-overlay@.service.in` and `units/vxlan-overlay@.service.in` — both are the systemd templated form (`@.service`). `${CLUSTER_ID}` is substituted at install time, `%i` carries the cluster id at runtime, and `WantedBy=multi-user.target` makes both units reboot-survivable once enabled. The VXLAN unit additionally carries `Requires=wg-overlay@%i.service` + `After=` so VXLAN never starts before the WG underlay; `${EXECSTART_BLOCK}` is rendered from the local peer table at install time and contains the `ip link add` plus per-peer `bridge fdb append` lines. |
| `tools/infra_pkg/adopt.sh` | Bash shim that delegates to `tools/infra adopt ...`. |
| `tools/infra_tests/` | Unit tests for the adopt-side pure helpers; no real SSH or network. |
| `.local/infra/inventory.json` | Adopted-host inventory (gitignored under `.local/`). |
| `.agents/personalities/<name>/personality.md` | Committed personality definition: YAML front matter (`name`, `title`, `cli`, `model`, `effort`, `mode`, `delegates_to`, `tools.shell_allowlist`, `clear_policy`) + role body. Reviewed like skills. No concrete GitHub login or org may appear here; use `<login>`/`<org>` placeholders. |
| `.agents/personalities/_defaults.yaml` | Per-CLI defaults: claude `claude-sonnet-4-6`, codex `gpt-5.5` low, copilot `gpt-5.4`. Plus `lock` (`ask_default_mode=wait`, `as_root_default_mode=fail`, `timeout=300s`, `stale_after=12h`) and `replay` (`max_turns=40`, `max_bytes=200000`, `drift_policy=refresh-and-continue`) blocks. |
| `.agents/skills/personality/` | Skill body for the multi-CLI personalities verb (issue #14). Routable from Claude/Codex/Copilot via the existing `.claude/skills`, `.codex/skills`, `.github/instructions/skills` symlinks. |
| `.agents/facet/personality/facet.json` | Facet manifest for the personalities slice: owned paths under `.agents/personalities/**`, `tools/personality`, `tools/personality_pkg/**`, `tools/personality_tests/**`. Declares the `personality` command and the `personality_tests` closeout check. |
| `tools/personality` | `personality` verb dispatcher (Python). Subcommands `list`, `init`, `as-root`, `ask`, `clear`. |
| `tools/personality_pkg/` | Implementation modules: `definitions.py` (YAML-subset front-matter + defaults parser), `state.py` (lock + state layout under `.local/personalities/`), `transcript.py` (append-only JSONL + replay-prompt builder), per-CLI adapters (`claude_adapter.py`, `codex_adapter.py`, `copilot_adapter.py`), `runner.py` (subprocess + exec wrapper), and `commands/` (one file per subcommand: `list_cmd.py`, `init_cmd.py`, `as_root_cmd.py`, `ask_cmd.py`, `clear_cmd.py`). |
| `tools/personality_tests/` | Unit tests covering definition parsing, defaults override, lock semantics, transcript replay round-trip, per-adapter argv shape, native-resume vs replay fallback, dispatch routing, and full `ask` round-trip with a stub CLI runner. CLI invocations are mocked. |
| `.local/personalities/<name>/` | Per-machine session state: `session_id`, `session_meta.yaml`, `transcript.jsonl`, `lock`, `last_invocation.json`, `last_stdout.txt`, `last_stderr.txt`, `replay_prompt.md`. Gitignored under `.local/`. |

## 8. Commands

| Command | Mode | Purpose |
|---------|------|---------|
| `initialize` | Python | Idempotent post-clone setup: render LICENSE/README, seed CONTEXT.md + docs/adr/ + target ledger + starter backlog, run setup + bootstrap + agent_check, stamp completion. |
| `agent` | Python | Query and maintain the repository agent knowledge base. |
| `agent_check` | Python | Validate skill routing, doc references, and Facet-backed command inventory. Rejects `_` in skill folder names. |
| `ideas` | Python | Manage idea inventory, scoring, readiness gates, learning-ledger queries, stale idea reports, and evidence-backed next-bet activation. |
| `setup` | Python | Install / status / uninstall managed git hooks and configured VSCode plugins. |
| `source_mirror` | Python | List or upload configured byte-identical upstream source mirrors. |
| `system_test` | Python | Run repo-level clustered plain and bwrap backend smoke tests from the scenario manifest. |
| `infra` | Python | Multi-provider VM fabric verb (ADR-0014). Subcommands adopt (SSH-reachable host onto the inventory; runtime-discovered GH login for keys-sync), status (list adopted hosts + last-known reachable), wg-up (per-host WireGuard keypair gen + config render + wg-overlay@cluster systemd unit install/enable/start; reboot-survivable via WantedBy=multi-user.target; private key mode 0600 owned root at /etc/wireguard/wg-c<cluster>.key and never crosses back over SSH), wg-peer-add (symmetric peer registration in inventory + re-render + restart on both hosts; static peer list, gossip lands later), vxlan-up (stack VXLAN overlay on top of WG: one VNI per cluster, head-end-replicated FDB for broadcast, inner overlay 10.<cluster>.<node_high>.<node_low>/16, default inner MTU 1370, install + enable vxlan-overlay@cluster systemd unit, render /etc/hosts block bracketed by BEGIN/END markers), and hosts-render (re-render the /etc/hosts block from the current peer table without touching VXLAN). deploy, provision land with later issues. |
| `personality` | Python | Multi-CLI persistent personalities verb (issue #14, spec docs/research/multi_cli_personality_skill_spec.md). Subcommands list (roster + last_active), init <name> --cli claude/codex/copilot (scaffold a definition), as-root <name> (interactive persistent session via native CLI resume or fresh seed; lock fail-fast), ask <name> "<prompt>" (one-shot non-interactive; native resume preferred, transcript replay fallback; stdout = reply only; lock waits by default), and clear <name> (wipe `.local/personalities/<name>/`; definition preserved). Definitions at `.agents/personalities/<name>/personality.md`; defaults at `.agents/personalities/_defaults.yaml`. Per-CLI defaults: claude claude-sonnet-4-6, codex gpt-5.5 low, copilot gpt-5.4. Cross-CLI delegation: personality ask <name> "<prompt>" works as a Bash command inside any CLI whose tool/shell allowlist permits it. |

## 6. Naming

- Files, directories, config keys, Python modules, generated
  identifiers, cache keys, and internal command names: **`_`**.
- CLI flags: **`-` / `--`** (conventional).
- Skill folder names under `.agents/skills/`: **`-`** only — external
  agent runtime discovery convention. `agent_check` rejects `_`
  here.
- Do not add hyphenated command aliases in this template; commands
  are named once with underscores. Exception: `pyext-build` keeps
  the issue-specified name for the mypyc extension builder.

## 7. Integrations

| Service | Default credential source | Notes |
|---------|---------------------------|-------|
| GitHub | `GITHUB_TOKEN` env, else `~/github.token` (mode `0600`). | Used by `gh` and any tool calling the GitHub API. Permissions on the file should be `0600`. |
| VM provider (Hetzner, etc.) | `~/<provider>.token` (mode `0600`). | Read by `bootstrap/providers/<name>.sh` for `create_vm`/`destroy_vm`/`list_vms`. Tokens stay on the operator's machine; never pushed to fabric hosts. See ADR-0014. |
| GH-keys-sync (per-host systemd timer) | `https://github.com/<login>.keys` over plain HTTPS. | Installed by `infra adopt`. The `<login>` is **runtime-discovered** by `GET /user` against `~/github.token` (or `GITHUB_TOKEN`); operator can override with `--ssh-keys-github=<other>` or disable via `--ssh-keys=<path>`. **No concrete login is hard-coded anywhere in this repo.** Default refresh interval 15 minutes. Unit template lives at `tools/infra_pkg/units/gh-keys-sync.service.in` with a `${LOGIN}` placeholder substituted at adopt time. |

### Toolchain

| Tool | Spec | Role |
|------|------|------|
| Python (musl CPython 3.14) | `bootstrap/tools/python.sh` | Repo machinery interpreter. See ADR-0008. |
| C/C++ (Zig + libc++) | `bootstrap/tools/zig.sh` | Single bundled C/C++ toolchain (clang + LLD + libc + libc++). Default target `*-linux-musl`; libstdc++ deliberately excluded. See ADR-0013. |
| librt (source-built mypyc runtime) | `bootstrap/tools/librt.sh` | Builds mypyc's native runtime helper from sdist with the pinned Zig musl ABI. |
| bwrap (Alpine minirootfs) | `bootstrap/tools/bwrap.sh` | Sandbox + musl loader source for the Python wrapper. |

When adding a new third-party integration, document it in this table
and in `README.md` Integrations. Read credentials from
`~/<service>.token` or an environment variable; never commit them to
the repo and never log them.

GitHub-derived identity (the `<login>` for SSH `authorized_keys` sync,
the `<org>` for self-hosted runners, the `ghcr.io` namespace for
systemd-deploy artifacts) is **discovered at runtime** via
`GET /user` against `~/github.token`. No tracked file in this repo
may contain a concrete GitHub login or org as a literal string.
Operators may override per host. See ADR-0014.

## 13. Operator runbook — 2-node WG underlay smoke

This is the live-host validation flow for ADR-0014's WireGuard
underlay. The agent does not run real SSH against hosts in tests;
the operator runs this manually after the code lands.

Pre-requisites:
- Two SSH-reachable hosts (BYO Contabo VPS or otherwise) accepting
  root or passwordless-sudo from the operator's workstation.
- `wireguard-tools` installed on both (`apt install wireguard-tools`
  on Debian/Ubuntu; `infra adopt` already probes `modprobe wireguard`).
- A free UDP port on each host for WG listen (default `51820`).

Steps (replace `<a>`, `<b>` with your `user@host` strings, `<C>` with
the cluster id, and pick distinct node ids):

```
./repo.sh infra adopt contabo <a> <C> 1
./repo.sh infra adopt contabo <b> <C> 2
./repo.sh infra wg-up <a>
./repo.sh infra wg-up <b>
./repo.sh infra wg-peer-add <a> <b>
```

Acceptance checks (run on each host):

```
ssh <a> 'wg show'
ssh <a> 'ping -c 3 10.200.<C>.2'
ssh <b> 'ping -c 3 10.200.<C>.1'
ssh <a> 'systemctl is-enabled wg-overlay@<C>.service'
ssh <a> 'sudo reboot' && sleep 60 && ssh <a> 'wg show'
```

Expected:
- `wg show` lists the other node's pubkey and a recent
  "latest handshake" timestamp.
- ICMP works in both directions over `10.200.<C>.x`.
- `systemctl is-enabled` prints `enabled` (reboot survival).
- After reboot, `wg show` again reports an active handshake without
  any operator intervention.

MTU: the underlay link is whatever the provider gives you (typically
1500 on commodity VPS). WireGuard's internal MTU lands around 1420
after the 80-byte WG header; do not lower further yet. The VXLAN
overlay (issue #5) defaults its inner MTU to 1370 on top of that.

Private-key invariants (CODE-REVIEWABLE):
- The private key only exists on the host at
  `/etc/wireguard/wg-c<cluster>.key`, mode `0600`, owned `root:root`.
  It is never written under the repo root and never crosses back
  over SSH from the host. Inventory carries the public key only.

### 13.1 VXLAN overlay + broadcast + /etc/hosts (issue #5)

After the WG underlay smoke above succeeds, layer VXLAN on top.
One VNI per cluster (`VNI == cluster_id`); FDB head-end-replicates
broadcast to each peer's WG underlay IP. Inner subnet is
`10.<C>.0.0/16` and inner MTU defaults to 1370.

```
./repo.sh infra vxlan-up <a>
./repo.sh infra vxlan-up <b>
./repo.sh infra hosts-render <a>
./repo.sh infra hosts-render <b>
```

Acceptance checks (run on each host):

```
ssh <a> 'ip -d link show vxlan-c<C>'
ssh <a> 'bridge fdb show dev vxlan-c<C>'
ssh <a> 'getent hosts node-2.c<C>'
ssh <a> 'ping -c 3 node-2.c<C>'
ssh <b> 'ping -c 3 node-1.c<C>'
ssh <a> 'systemctl is-enabled vxlan-overlay@<C>.service'
```

Broadcast smoke (one shell per node):

```
# receiver on <b>
ssh <b> 'socat -u UDP-RECVFROM:9999,reuseaddr,fork -'
# sender on <a>
ssh <a> 'echo hi-c<C> | socat -u - UDP-DATAGRAM:10.<C>.255.255:9999,broadcast,reuseaddr'
```

Expected:
- `ip -d link show vxlan-c<C>` reports `vxlan id <C> dev wg-c<C>
  dstport 4789 nolearning` and `mtu 1370`.
- `bridge fdb show` lists a `00:00:00:00:00:00 ... dst 10.200.<C>.x`
  entry for every other peer.
- `node-<id>.c<C>` resolves on every node and round-trips ICMP.
- `socat` receiver on the broadcast port prints `hi-c<C>`.
- `systemctl is-enabled` prints `enabled` (reboot survival).

Cross-cluster isolation (CODE-REVIEWABLE + OPERATOR-VALIDATION):
two clusters on the same hosts use distinct VNIs and distinct FDBs,
so a broadcast on `10.<C1>.255.255` does not appear on
`vxlan-c<C2>`. `nolearning` plus per-VNI head-end FDB enforces this.
To validate live, repeat the broadcast smoke with cluster `<C2>` and
observe the `<C1>` receiver gets nothing.

Inner MTU override (per cluster, at vxlan-up time):

```
./repo.sh infra vxlan-up <a> --mtu 1280
./repo.sh infra vxlan-up <b> --mtu 1280
```

`/etc/hosts` invariants (CODE-REVIEWABLE):
- The managed block is bracketed by
  `# BEGIN core-infra c<C>` / `# END core-infra c<C>` lines and
  replaces only the bracketed region. Re-running `hosts-render`
  yields a byte-identical file.

## 14. CI

CI restores `.local/toolchain/` plus `.local/stamps/` with
`actions/cache/restore`, runs the bootstrap and agent checks through
`./repo.sh`, and saves those bootstrap paths only from non-PR runs on
cache misses. Cache keys are scoped by architecture and by
`bootstrap/vars/local_cache_key.sh`, `.agents/repo.json`, and
`bootstrap/tools/*.sh`. The bootstrap Facet owns CI bootstrap/cache
policy in `ci.yml`; the maintenance Facet owns scheduled cache
warming. Repo Python
commands run through the pinned musl CPython 3.14 installed by
`bootstrap/tools/python.sh`; its wrapper uses the bootstrapped Alpine
musl loader from the bwrap bootstrap. `python.sh` declares
`TOOL_DEPS=(bwrap)`, so `repo.sh` dependency planning runs bwrap before
Python and the host does not need musl installed. Alpine/static
product portability is the baseline. Fast-Python hot paths compile
with pinned `mypy[mypyc]` and the Zig musl toolchain; output `.so`
modules ship with products while mypyc stays on dev/CI machines.
`bootstrap/tools/librt.sh` source-builds mypyc's native runtime helper
with the same Zig musl ABI. CI also runs `./repo.sh system_test`,
whose base primitive is a three-node cluster. Every node gets the same
guest service port from the scenario manifest and a distinct cluster
IP; host-side ports are assigned per node for external reachability
while guests reach each other directly through cluster IP plus service
port. The Template smoke test validates that topology without requiring
live socket binds, using host-global lock-file claims under
`$REPO_LOCAL/locks/system_test/` for node-name/IP uniqueness. Bwrap
nodes receive a generated `/etc/hosts` mapping (`node-0`, `node-1`,
...).

`cache_warm.yml` is a maintenance Facet cron job. It periodically
restores the same cache keys to reset GitHub's LRU timer. `maintenance.yml`
runs stale-doc and idea-inventory hygiene. Restore misses are
acceptable and must not fail the workflow. Add future scheduled repo
upkeep under `.agents/facet/maintenance/` unless a more specific Facet
clearly owns it.

## 15. Subsystems

| Subsystem | Layer | Purpose | Detail |
|-----------|-------|---------|--------|

(The template ships with no subsystems. Products add rows here as
they grow.)
