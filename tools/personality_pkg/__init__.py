"""Personality verb implementation (issue #14, spec in
docs/research/multi_cli_personality_skill_spec.md).

The verb dispatcher entry point lives at `tools/personality`. The
supporting modules — definitions, state, transcript, per-CLI adapters,
and subcommand handlers — live here so the dispatcher stays a single
file that `agent_check` can locate via `tools/<command>` while related
code groups together under `tools/personality_pkg/`.
"""
