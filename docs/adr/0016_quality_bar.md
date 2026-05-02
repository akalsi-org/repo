# 0016: Undeniable Quality Contract

## Status

Accepted.

## Context

The Template now carries enough automation that weak local checks become
expensive later. Quality gates must be repo-local, cheap to run, and
visible through `./repo.sh` so Products inherit the same contract.

## Decision

The quality bar is a staged contract:

- Q1: strict Python typing via `./repo.sh mypy ...`.
- Q2: lint/format/shell checks via `./repo.sh lint`.
- Q3: unit tests and repo-wide coverage via `./repo.sh test --coverage --min=85`.
- Q4: hard managed hooks. Agents must not bypass hooks with `--no-verify`.
- Q5: CI runs quality, tests, smokes, and docs on x86_64 and aarch64.
- Q6: committed schemas validate repo-truth JSON surfaces.
- Q7: docs links and command ADR coverage are checked by `agent_check`.
- Q8: reproducibility verification checks pinned tool inputs.
- Q9: dependency-shape verification rejects unpinned runtime deps.

External linters remain accelerators. Internal repo machinery must keep
fallback-free truth: if a configured gate is unavailable, the owning
command fails loudly or uses a documented stdlib check with narrower
coverage.

## Consequences

- Command Facet owns quality commands.
- Git hook Facet owns hook install/status behavior.
- CI mirrors local gates.
- Future quality work lands as small slices with explicit checks.
