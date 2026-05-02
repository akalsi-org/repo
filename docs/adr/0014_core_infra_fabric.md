# Core infra: WireGuard underlay + VXLAN overlay + gossip discovery

The template grows a `core-infra-lead` agent role and a multi-provider
VM fabric. This ADR locks the design before any exec code lands. The
fabric is the substrate that subsequent verbs (`infra adopt`, `infra
status`, `infra wg-up`, `infra deploy`, ...) operate on; later issues
(#3 onward) implement those verbs against this contract.

## Decision summary

- **Underlay:** WireGuard. Kernel-native, encrypted, multi-provider
  over the wider internet.
- **Overlay:** VXLAN, one VNI per cluster, kernel-native. Gives L2 +
  broadcast natively. Inner MTU defaults to 1370.
- **Discovery:** gossip over the VXLAN broadcast address, SWIM-style
  failure detection. No central ledger. A provision-time seed list of
  one to three peers bootstraps the chicken-and-egg: a new node
  WG-handshakes any one alive seed and gossip teaches it the rest.
- **Sub-grouping at the fabric layer:** none. Broadcast is the only
  fabric-level group primitive. Sub-group communication is an
  app-layer concern, addressed via unicast against numeric-ID
  hostnames.
- **Identity:** cluster ID is `u8` (1..255), node ID is `u16`
  (1..65535). Overlay IPv4 is `10.<cluster>.<node_high>.<node_low>`.
  WG underlay IPv4 is a separate `10.200.<cluster>.<node_low>/16`
  range. Hostname format is `node-<id>.c<cluster>`, rendered into
  `/etc/hosts` on each node from its local peer table.
- **Provider model:** two layers, pluggable from day 1.
  1. *Inventory + adopt* — pure SSH. Brings any SSH-accessible host
     (BYO Contabo VPS, laptop, RPi) onto the fabric. Provider label is
     metadata, not API.
  2. *Provisioning* — `bootstrap/providers/<name>.sh` exposes
     `create_vm` / `destroy_vm` / `list_vms` / `region_list` /
     `size_list`. Hetzner is the first concrete provider, in a later
     issue.
- **Credentials:** `~/<provider>.token` mode `0600`, matching the
  existing `~/github.token` convention.
- **Host tuning:** network sysctls + `tuned-adm profile
  network-throughput` at adopt/provision time. Inner VXLAN MTU defaults
  to 1370. `nosmt` is *conditional* (see below).
- **App layer:** bare systemd units deployed from a manifest. No
  Nomad, no Docker, no K8s for v1. Containers can be added later as a
  deploy target without changing the fabric.
- **GitHub integration:** every GitHub-derived value is discovered at
  runtime. No concrete GitHub login or org may appear as a hard-coded
  literal anywhere in tracked files.

## Why this stack

WireGuard alone is fast and simple but gives only L3 unicast: no L2,
no broadcast, no ARP. We want gossip to ride a broadcast the kernel
already does for us, and we want app-layer service discovery and
cluster-internal naming to feel like a single LAN. Adding VXLAN on top
of WG gives us that L2 illusion across the wider internet for the
cost of one more kernel module and one VNI per cluster.

We deliberately skip multicast because the wider internet has no
underlay multicast routing — any overlay multicast becomes N-unicast
replication anyway. Gossip + broadcast is the simplest thing that
works and is what SWIM already assumes.

The `10.<cluster>.<node_high>.<node_low>` overlay scheme keeps
identity arithmetic trivial: a cluster fits a `/16`, a node ID drops
straight into the last two octets. The separate `10.200.<cluster>.x`
WG range keeps underlay reachability debuggable independently of
overlay routing — if a node's overlay IP is silent you can still SSH
or `wg` it via the underlay. Hostnames embed the numeric IDs so app
code never has to invent a separate naming layer.

## Provider model

The two layers are pluggable from day 1 because we never want the
fabric to assume a specific cloud. Adopt is pure SSH on purpose: it
makes any reachable host a first-class fabric member without the
provisioning side-channel. Provisioning is the optional second step —
when a host should be created and destroyed by us, a provider script
under `bootstrap/providers/<name>.sh` exposes the CRUD surface and
nothing else. Provider tokens follow the existing `~/<service>.token`
mode-`0600` convention so `repo.sh` and `infra` verbs read them
identically and the rule "never commit credentials, never log them"
stays one rule.

## Host tuning

`nosmt` is conditional. We detect "Thread(s) per core" via `lscpu` and
only apply `nosmt` on dedicated/bare-metal hosts where SMT siblings
are guest-visible *and* the operator opts in per host. The default on
VPS guests is to leave SMT alone: the hypervisor already decides
sibling visibility, and the guest's `nosmt` is either a no-op or
halves visible vCPUs for no benefit. Network sysctls and `tuned-adm
profile network-throughput` are applied at adopt/provision time on
every host; those are uniformly safe.

## App layer

v1 deploys bare systemd units from a manifest. No Nomad, no Docker, no
K8s. Containers, when needed, are a deploy target the manifest can
emit without changing the fabric: the fabric just owns reachable
hosts with stable IPs and names. Picking systemd first keeps the
debugging surface (`systemctl`, `journalctl`) one most operators
already know and avoids a dependency on a control-plane that would
itself need bootstrapping over the same fabric.

## GitHub integration: runtime discovery, no hard-coding

Three places intersect GitHub and would be tempting to hard-code:

1. SSH `authorized_keys` synced from `https://github.com/<login>.keys`.
2. The org for self-hosted Actions runners (issue #11).
3. The `ghcr.io` namespace for systemd-deploy artifacts (issue #12).

For all three, `<login>` and `<org>` are discovered at runtime. SSH
key sync resolves `<login>` via `GET /user` against `~/github.token`;
runner registration and image pulls resolve their org and namespace
the same way. Operators may override per-host, but the default is
discovered, never literal. No tracked file in this repo may contain a
concrete GitHub login or org as a string. `agent_check` and review
should treat any such literal as a regression of this ADR.

The reason is reuse. The whole template is fork-and-rename; baking
one operator's GitHub identity into the substrate breaks that loop.
Runtime discovery costs one API call and removes a class of fork
hazards forever.

## Identity scheme — exact form

- Cluster ID: `u8`, valid range 1..255.
- Node ID: `u16`, valid range 1..65535.
- Overlay IPv4: `10.<cluster>.<node_high>.<node_low>` where
  `<node_high>` and `<node_low>` are the high and low bytes of the
  `u16` node ID.
- WG underlay IPv4: `10.200.<cluster>.<node_low>/16`. Underlay does
  not need the full node ID in the address; it only needs to reach the
  WG endpoint, and the overlay carries identity.
- Hostname: `node-<id>.c<cluster>` (decimal, no padding). Each node
  renders the cluster's peer table into `/etc/hosts` so name
  resolution is local and gossip-driven, not DNS-driven.

## Alternatives rejected

- **WG only, no VXLAN.** Loses L2, broadcast, ARP. Forces every
  service-discovery question onto a userspace layer. Rejected: VXLAN
  costs us almost nothing and gives gossip its natural transport.
- **IPSec + VXLAN instead of WG + VXLAN.** Same overlay capabilities,
  three to five times the config surface, harder to debug. IPSec wins
  only when audit/compliance demands cert-based IKE; we have no such
  requirement.
- **Tinc / n2n.** Userspace mesh VPNs, slower, not kernel-native.
  Rejected per the kernel-native requirement.
- **Provider VPC / cloud-native networking.** Locks to one provider,
  often costs extra, does not span the wider internet. Rejected: the
  whole point of this fabric is multi-provider over the open
  internet.
- **Central ledger (push or pull) for membership.** Adds a single
  point of failure and a transport. Gossip over the overlay we already
  have is strictly simpler.

## Consequences

- A new agent role, `core-infra-lead`, owns the fabric and its verb
  surface. The role is paper-trail-only in this slice; subsequent
  issues attach exec code.
- New paths land in later issues:
  - `bootstrap/providers/<name>.sh` for provisioning plugins.
  - `tools/infra/` for the `infra` verb implementation.
- A new `core_infra` Facet owns those paths plus the agent role
  manifest under `.agents/skills/core-infra-lead/`.
- The `infra` verb appears as a placeholder in README and AGENTS
  Verbs/Commands surfaces. Its subcommands are filled in by issue #3.
- `.gitignore` grows credential-shaped patterns (`*.token`, `*.key`,
  `*.pem`, `.env`) so a new fork cannot accidentally commit a provider
  or runner credential.
- Forks that want a different overlay scheme must amend this ADR
  rather than work around it; the identity arithmetic is a load-bearing
  contract for app-layer naming.

## Related issues

- #1: this slice — paper trail.
- #3: implement the `infra` verb skeleton + adopt/status/wg-up/deploy
  subcommands.
- #6, #7, #8, #9: fabric-side milestones (gossip, peer table render,
  cluster smoke, manifest deploy) layered onto #3.
- #11: self-hosted Actions runners; org discovered at runtime.
- #12: systemd-deploy artifacts via `ghcr.io`; namespace discovered at
  runtime.
