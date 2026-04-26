# Facets for repo capabilities

We use declarative Facets under `.agents/facet/<key>/facet.json` as
the source of truth for repo-level AI capabilities: owned paths,
commands, checks, documentation projections, and suggested
considerations. Facet presence means enabled; `.agents/repo.json`
holds Product knobs and optional per-Facet configuration, not a
separate enabled list. Internal repo machinery uses Facet truth
directly and fails loudly when it is missing; fallbacks are reserved
for released artifacts, production paths, credentials, and
cache/mirror accelerators where graceful degradation is part of the
contract.

The root Facet is stored at `.agents/facet/root/facet.json` and has
display name `/`. Every path should have one primary owner Facet;
other Facets may declare `consider` entries for suggested
thinking/routing only, never mandatory closeout checks. This preserves
clear responsibility while keeping cross-cutting awareness cheap.

## Considered options

- Keep command, KB, hook, and bootstrap truth scattered across
  `.agents/repo.json`, tools, and docs. Rejected because it makes
  ideation cheap but execution drift-prone.
- Add a plugin runtime where Facets execute lifecycle hooks. Rejected
  for now because executable plugins increase security and maintenance
  surface; existing tools should consume declarative Facet truth.
- Maintain an explicit enabled-Facet list in `.agents/repo.json`.
  Rejected because presence-as-enabled avoids duplicate inventory and
  "file exists but disabled" ambiguity.
