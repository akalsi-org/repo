---
name: core-infra-lead
description: Use when standing up, adopting, or operating the multi-provider VM fabric defined in ADR-0014 — WireGuard underlay, VXLAN overlay, gossip discovery, and the `infra` verb surface. Activates on edits under `.agents/facet/core_infra/`, `bootstrap/providers/`, `tools/infra/`, or any operation that touches cluster identity, peer tables, host tuning, provider tokens, or systemd-deploy manifests.
---

# core-infra-lead

Owns the fabric defined in `docs/adr/0014_core_infra_fabric.md`. The
fabric is the substrate every product runtime sits on; this role
reads the ADR as the contract and refuses to drift from it.

## When this skill activates

- A user asks to adopt a new host (`infra adopt <user@host>`),
  inspect cluster state (`infra status`), bring up WireGuard (`infra
  wg-up`), or roll out a manifest (`infra deploy`).
- An edit touches `.agents/facet/core_infra/`, `bootstrap/providers/`,
  `tools/infra/`, or anything that changes cluster identity, peer
  rendering, or host tuning.
- A new provider plugin is added under `bootstrap/providers/<name>.sh`.
- Adopting a BYO host (Contabo VPS, laptop, RPi) onto an existing
  cluster.

## Owned commands (verb surface)

The `infra` verb and its subcommands are the operator surface.
Concrete implementations land in issue #3; this skill is the contract.

| Subcommand | Purpose |
|------------|---------|
| `infra adopt` | SSH to a target host, install WG + VXLAN + tuning, register it in the local peer table, hand it the seed list, gossip teaches it the rest. |
| `infra status` | Print cluster membership from the local peer table plus liveness from the last gossip round. |
| `infra wg-up` | Re-derive WG config from `.agents/repo.json` + peer table, push to host, restart the unit. Idempotent. |
| `infra deploy` | Render systemd unit manifest, copy units, `systemctl daemon-reload` + enable + start. No Nomad, no Docker. |
| `infra provision` | (Optional, when a provider plugin is configured) `create_vm` / `destroy_vm` / `list_vms` against `bootstrap/providers/<name>.sh`. |

## Read first

- `docs/adr/0014_core_infra_fabric.md` — the contract. Re-read on
  every non-trivial change.
- `.agents/facet/core_infra/facet.json` — owned paths and checks.
- `bootstrap/providers/<name>.sh` for the provider you are touching.
- `~/<provider>.token` (mode `0600`) for credentials. Never echo,
  never log.

## Identity arithmetic — do not improvise

- Cluster ID: `u8`, 1..255.
- Node ID: `u16`, 1..65535.
- Overlay IPv4: `10.<cluster>.<node_high>.<node_low>`.
- WG underlay IPv4: `10.200.<cluster>.<node_low>/16`.
- Hostname: `node-<id>.c<cluster>` (decimal, no padding).
- Each node renders its peer table into `/etc/hosts`. DNS is not in
  the fabric.

If a user asks for a different scheme, treat it as an ADR amendment,
not a config knob. The arithmetic is load-bearing for app-layer
naming.

## Host tuning rules

- Network sysctls + `tuned-adm profile network-throughput` at
  adopt/provision time. Always.
- Inner VXLAN MTU defaults to 1370.
- `nosmt` is *conditional*. Detect "Thread(s) per core" via `lscpu`.
  Only apply on dedicated/bare-metal where SMT siblings are
  guest-visible *and* the operator opts in per host. Default on VPS
  guests: leave SMT alone.

## GitHub integration — runtime discovery only

`<login>` for SSH `authorized_keys` sync, `<org>` for self-hosted
Actions runners (#11), and the `ghcr.io` namespace for systemd-deploy
artifacts (#12) are discovered at runtime via `GET /user` against
`~/github.token`. Operators may override per host; the default is
always discovered.

This is a hard rule, not a preference. No tracked file in this repo
may contain a concrete GitHub login or org as a literal. ADR-0014
documents the rule; review treats any literal as a regression.

## What NOT to do

- **Do not** hard-code a GitHub login or org anywhere — not in
  scripts, not in unit files, not in docs templates. Discover at
  runtime.
- **Do not** push provider tokens onto hosts. Tokens stay on the
  operator's machine at `~/<provider>.token` mode `0600`; the host
  receives only the WG private key it generates locally and any
  per-host secrets the manifest declares.
- **Do not** apply `nosmt` unconditionally. Detect first, default to
  off on VPS guests, opt-in on bare metal.
- **Do not** add a central ledger for membership. Gossip over the
  overlay broadcast is the source of truth; a ledger reintroduces a
  single point of failure ADR-0014 specifically rejects.
- **Do not** introduce userspace mesh VPNs (Tinc, n2n) or
  provider-locked VPC networking. Kernel-native WG + VXLAN only.
- **Do not** add Nomad/Docker/K8s to v1 deploy. Bare systemd until a
  product decides otherwise and amends the ADR.
- **Do not** treat caches or accelerators as load-bearing — the
  template-wide rule applies here too. A miss must not break a fresh
  fabric stand-up.

## Closeout

- `./repo.sh agent_check` clean.
- `git diff --check` clean.
- If the change touches the ADR contract (identity, tuning, provider
  surface, GitHub-discovery rule), update `docs/adr/0014_core_infra_fabric.md`
  in the same commit.
- New provider script under `bootstrap/providers/`? Add the file
  pattern to `.agents/facet/core_infra/facet.json` `owns` only if the
  pattern is not already covered by a `**` glob.
