# Cluster-first system tests

The Template's `system_test` command treats a cluster, not a single
host, as the base runtime primitive. Even the initial smoke test
allocates three nodes (`node-0`, `node-1`, `node-2`) with distinct
cluster IPs, distinct host-visible port assignments, and the same
guest service port.

Plain and bwrap backends share this cluster model. The bwrap backend
uses the bootstrapped Alpine rootfs + bubblewrap shim and shares host
networking so guest ports are reachable from the host; each guest also
gets a generated `/etc/hosts` file so cluster node names resolve
inside the sandbox. Each node may use the same service port because
the cluster identity is the node IP/name plus guest port; host-side
port assignments are separate and exist only for outside access. Nodes
inside the cluster reach each other directly through cluster IP plus
service port. The
Template smoke test intentionally validates declared topology without
live socket reservation because outer agent sandboxes can deny bind
operations; bwrap shares host networking and cannot grant permissions
the outer sandbox withholds. Instead, the Template smoke test uses
host-global lock-file claims under `$REPO_LOCAL/locks/system_test/`
to assert node-name/IP uniqueness deterministically across concurrent
worktrees sharing `.local`. Those locks are advisory and held only for
the command lifetime, so stale `.local` state does not become
load-bearing. Product-specific scenarios that need real service
readiness can add live bind/connect checks once they own that runtime.
Missing
bwrap/rootfs or kernel-disallowed
unprivileged user namespaces skip cleanly rather than failing the
whole system test.

We chose this over a single-host smoke test because reliability and
resilience bugs appear at topology boundaries: name resolution,
per-node scratch state, address allocation, and host/guest port
visibility. Starting with cluster semantics keeps future Product
system tests from having to migrate their mental model later.
