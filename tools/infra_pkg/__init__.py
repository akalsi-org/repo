"""Infra fabric verb implementation (ADR-0014).

The package layout is split out from `tools/infra` (the executable
verb dispatcher) so the dispatcher stays a single discoverable file
that `agent_check` can locate via `tools/<command>` while the
supporting code (adopt logic, inventory, GH discovery, systemd unit
templates) lives next to it under `tools/infra_pkg/`.
"""
