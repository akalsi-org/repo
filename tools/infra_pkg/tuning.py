"""Network sysctls + tuned profile shim used by adopt.

Pure data + small renderers. The actual `sysctl --system` and
`tuned-adm` runs are issued by adopt over SSH.
"""
from __future__ import annotations


SYSCTL_SETTINGS: tuple[tuple[str, str], ...] = (
  # Larger socket buffers for >1 GbE long-fat-pipe overlay traffic.
  ("net.core.rmem_max", "16777216"),
  ("net.core.wmem_max", "16777216"),
  ("net.core.rmem_default", "1048576"),
  ("net.core.wmem_default", "1048576"),
  ("net.core.netdev_max_backlog", "5000"),
  # UDP buffer pressure thresholds (pages). VXLAN + WG ride UDP.
  ("net.ipv4.udp_mem", "8388608 12582912 16777216"),
  ("net.ipv4.udp_rmem_min", "65536"),
  ("net.ipv4.udp_wmem_min", "65536"),
  # TCP sane-network defaults.
  ("net.ipv4.tcp_rmem", "4096 1048576 16777216"),
  ("net.ipv4.tcp_wmem", "4096 1048576 16777216"),
  ("net.ipv4.tcp_mtu_probing", "1"),
  ("net.ipv4.tcp_congestion_control", "bbr"),
  ("net.ipv4.tcp_notsent_lowat", "131072"),
)


SYSCTL_DROPIN_PATH = "/etc/sysctl.d/90-infra-fabric.conf"


def render_sysctl_dropin() -> str:
  lines = [
    "# managed by infra adopt; ADR-0014 host-tuning rules",
    "# do not edit by hand; re-run infra adopt to refresh",
  ]
  for key, value in SYSCTL_SETTINGS:
    lines.append(f"{key} = {value}")
  lines.append("")
  return "\n".join(lines)


# Hand-rolled fallback when tuned-adm is not installed. Mirrors the
# headline knobs in tuned's network-throughput profile (kernel.sched
# autogroup, vm.dirty_ratio, transparent hugepages).
TUNED_FALLBACK_SETTINGS: tuple[tuple[str, str], ...] = (
  ("kernel.sched_autogroup_enabled", "1"),
  ("vm.dirty_ratio", "40"),
  ("vm.dirty_background_ratio", "10"),
  ("vm.swappiness", "10"),
)
TUNED_FALLBACK_DROPIN_PATH = "/etc/sysctl.d/91-infra-tuned-fallback.conf"


def render_tuned_fallback_dropin() -> str:
  lines = [
    "# managed by infra adopt; tuned-adm not present, hand-rolled equivalent",
    "# documented gap: install tuned for proper transparent_hugepage handling",
  ]
  for key, value in TUNED_FALLBACK_SETTINGS:
    lines.append(f"{key} = {value}")
  lines.append("")
  return "\n".join(lines)
