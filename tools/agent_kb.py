"""Repo-state index + query engine for `agent`.

`agent` is the front-end: it compiles repo-state inputs into ignored cached
JSONL shards, then answers agent requests through named queries and runtime
table actions.

Editable repo-state inputs live in `.agents/kb-src/**/*.jsonl`. Ignored runtime
cache lives under `build/agent-kb/` as:

- `manifest.json` — source hashes + shard summaries.
- `shards/*.jsonl` — one compiled shard per source JSONL file.
- `runtime/*.jsonl` — writable runtime tables for request / feedback loops.

The cache is intentionally sharded so rebuilds can rewrite only changed source
units and so future indexing passes can fan out in parallel cheaply.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import sys
from dataclasses import dataclass

from tools.agent_check import glob_match

KB_SRC_REL = ".agents/kb-src"
KB_TABLES_REL = f"{KB_SRC_REL}/tables"
KB_BUILD_REL = "build/agent-kb"
MANIFEST_REL = f"{KB_BUILD_REL}/manifest.json"
SHARDS_REL = f"{KB_BUILD_REL}/shards"
RUNTIME_REL = f"{KB_BUILD_REL}/runtime"
SCHEMA_VERSION = 1

_GLOB_CHARS = set("*?[{")


class KbError(RuntimeError):
  """Raised for invalid KB source data or cache failures."""


@dataclass(frozen=True)
class CompiledFact:
  id: str
  says: tuple[str, ...]
  paths: tuple[str, ...]
  verbs: tuple[str, ...]
  phases: tuple[str, ...]
  skills: tuple[str, ...]
  refs: tuple[str, ...]
  checks: tuple[str, ...]
  read_next: tuple[str, ...]
  priority: int
  prefixes: tuple[str, ...]
  source: str
  line: int

  def to_json(self) -> dict[str, object]:
    return {
      "id": self.id,
      "says": list(self.says),
      "paths": list(self.paths),
      "verbs": list(self.verbs),
      "phases": list(self.phases),
      "skills": list(self.skills),
      "refs": list(self.refs),
      "checks": list(self.checks),
      "read_next": list(self.read_next),
      "priority": self.priority,
      "prefixes": list(self.prefixes),
      "source": self.source,
      "line": self.line,
    }


@dataclass(frozen=True)
class SourceTableRow:
  table: str
  payload: dict[str, object]
  source: str
  line: int

  def to_json(self) -> dict[str, object]:
    return {
      "table": self.table,
      "source": self.source,
      "line": self.line,
      **self.payload,
    }


@dataclass(frozen=True)
class ProbeResult:
  facts: tuple[CompiledFact, ...]
  skills: tuple[str, ...]
  missing_skills: tuple[str, ...]
  checks: tuple[str, ...]
  refs: tuple[str, ...]
  read_next: tuple[str, ...]
  scanned_shards: tuple[str, ...]

  def to_json(self) -> dict[str, object]:
    return {
      "skills": list(self.skills),
      "missing_skills": list(self.missing_skills),
      "checks": list(self.checks),
      "refs": list(self.refs),
      "read_next": list(self.read_next),
      "scanned_shards": list(self.scanned_shards),
      "facts": [fact.to_json() for fact in self.facts],
    }


def _repo_root(root: str | pathlib.Path | None) -> pathlib.Path:
  if root is None:
    env = os.environ.get("REPO_ROOT")
    return pathlib.Path(env or os.getcwd()).resolve()
  return pathlib.Path(root).resolve()


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
  return path.relative_to(root).as_posix()


def _kb_src_dir(root: pathlib.Path) -> pathlib.Path:
  return root / KB_SRC_REL


def _kb_tables_dir(root: pathlib.Path) -> pathlib.Path:
  return root / KB_TABLES_REL


def _manifest_path(root: pathlib.Path) -> pathlib.Path:
  return root / MANIFEST_REL


def _shards_dir(root: pathlib.Path) -> pathlib.Path:
  return root / SHARDS_REL


def _runtime_dir(root: pathlib.Path) -> pathlib.Path:
  return root / RUNTIME_REL


def _discover_sources(root: pathlib.Path) -> list[pathlib.Path]:
  src_dir = _kb_src_dir(root)
  if not src_dir.is_dir():
    return []
  tables_dir = _kb_tables_dir(root)
  return sorted(
    path
    for path in src_dir.rglob("*.jsonl")
    if not str(path).startswith(str(tables_dir))
  )


def _discover_table_sources(root: pathlib.Path) -> list[pathlib.Path]:
  tables_dir = _kb_tables_dir(root)
  if not tables_dir.is_dir():
    return []
  return sorted(tables_dir.rglob("*.jsonl"))


def _hash_file(path: pathlib.Path) -> str:
  h = hashlib.sha256()
  with path.open("rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
      h.update(chunk)
  return h.hexdigest()


def _read_json(path: pathlib.Path) -> dict[str, object] | None:
  if not path.is_file():
    return None
  return json.loads(path.read_text(encoding="utf-8"))


def _json_text(value: object) -> str:
  return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _write_text_if_changed(path: pathlib.Path, text: str) -> bool:
  if path.is_file() and path.read_text(encoding="utf-8") == text:
    return False
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_name(f".{path.name}.tmp")
  tmp.write_text(text, encoding="utf-8")
  os.replace(tmp, path)
  return True


def _read_lines(path: pathlib.Path) -> list[str]:
  return path.read_text(encoding="utf-8").splitlines()


def _normalize_str_list(
    raw: object, *, field: str, source: str, line: int
) -> tuple[str, ...]:
  if raw is None:
    return ()
  if isinstance(raw, str):
    return (raw,)
  if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
    raise KbError(f"{source}:{line}: `{field}` must be string or list[str]")
  return tuple(raw)


def _ref_path_exists(root: pathlib.Path, ref: str) -> bool:
  path = ref.split("#", 1)[0]
  if not path:
    return False
  return (root / path).exists()


def _looks_globby(path: str) -> bool:
  return any(ch in path for ch in _GLOB_CHARS)


def _static_prefix(pattern: str) -> str:
  if not pattern:
    return ""
  if not _looks_globby(pattern):
    return pattern
  parts: list[str] = []
  for seg in pattern.split("/"):
    if _looks_globby(seg):
      break
    parts.append(seg)
  if not parts:
    return ""
  prefix = "/".join(parts)
  if pattern != prefix and not prefix.endswith("/"):
    prefix += "/"
  return prefix


def _score_fact(fact: CompiledFact, paths: tuple[str, ...]) -> tuple[int, int, str]:
  if not paths:
    prefix_score = max((len(p) for p in fact.prefixes), default=0)
    return (fact.priority, prefix_score, fact.id)
  best = 0
  for pat in fact.paths:
    prefix = _static_prefix(pat)
    for path in paths:
      if prefix and path.startswith(prefix):
        best = max(best, len(prefix))
      elif glob_match(path, pat):
        best = max(best, len(pat))
  return (fact.priority, best, fact.id)


def _fact_matches(
    fact: CompiledFact,
    *,
    paths: tuple[str, ...],
    verb: str | None,
    phase: str | None,
) -> bool:
  if paths and fact.paths:
    if not any(glob_match(path, pat) for path in paths for pat in fact.paths):
      return False
  if verb and fact.verbs and verb not in fact.verbs:
    return False
  if phase and fact.phases and phase not in fact.phases:
    return False
  return True


def _known_skills(root: pathlib.Path) -> set[str]:
  skill_dir = root / ".agents/skills"
  if not skill_dir.is_dir():
    return set()
  return {path.parent.name for path in skill_dir.glob("*/SKILL.md")}


def _parse_source_file(
    root: pathlib.Path,
    path: pathlib.Path,
    known_skills: set[str],
) -> list[CompiledFact]:
  rel = _rel(root, path)
  out: list[CompiledFact] = []
  for line_no, raw_line in enumerate(_read_lines(path), start=1):
    line = raw_line.strip()
    if not line:
      continue
    try:
      raw = json.loads(line)
    except json.JSONDecodeError as exc:
      raise KbError(f"{rel}:{line_no}: invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
      raise KbError(f"{rel}:{line_no}: fact must be a JSON object")
    fact_id = raw.get("id")
    if not isinstance(fact_id, str) or not fact_id:
      raise KbError(f"{rel}:{line_no}: `id` must be a non-empty string")
    says = _normalize_str_list(raw.get("says"), field="says", source=rel, line=line_no)
    summary = raw.get("summary")
    if summary is not None:
      if not isinstance(summary, str) or not summary:
        raise KbError(f"{rel}:{line_no}: `summary` must be a non-empty string")
      says = says or (summary,)
    if not says:
      raise KbError(f"{rel}:{line_no}: fact needs `says` or `summary`")
    paths = _normalize_str_list(raw.get("paths"), field="paths", source=rel, line=line_no)
    verbs = _normalize_str_list(raw.get("verbs"), field="verbs", source=rel, line=line_no)
    phases = _normalize_str_list(raw.get("phases"), field="phases", source=rel, line=line_no)
    skills = _normalize_str_list(raw.get("skills"), field="skills", source=rel, line=line_no)
    refs = _normalize_str_list(raw.get("refs"), field="refs", source=rel, line=line_no)
    checks = _normalize_str_list(raw.get("checks"), field="checks", source=rel, line=line_no)
    read_next = _normalize_str_list(
      raw.get("read_next"), field="read_next", source=rel, line=line_no
    )
    priority_raw = raw.get("priority", 0)
    if not isinstance(priority_raw, int):
      raise KbError(f"{rel}:{line_no}: `priority` must be an int")
    for skill in skills:
      if skill not in known_skills:
        raise KbError(f"{rel}:{line_no}: unknown skill `{skill}`")
    for ref in refs:
      if not _ref_path_exists(root, ref):
        raise KbError(f"{rel}:{line_no}: ref path missing: {ref}")
    for exact in paths:
      if not _looks_globby(exact) and not (root / exact).exists():
        raise KbError(f"{rel}:{line_no}: path missing: {exact}")
    prefixes = tuple(sorted({_static_prefix(pat) for pat in paths} or {""}))
    out.append(
      CompiledFact(
        id=fact_id,
        says=says,
        paths=paths,
        verbs=verbs,
        phases=phases,
        skills=skills,
        refs=refs,
        checks=checks,
        read_next=read_next,
        priority=priority_raw,
        prefixes=prefixes,
        source=rel,
        line=line_no,
      )
    )
  return out


def _table_name_from_source(root: pathlib.Path, path: pathlib.Path) -> str:
  rel = path.relative_to(_kb_tables_dir(root)).with_suffix("").as_posix()
  return rel.replace("/", "__")


def _parse_table_source(root: pathlib.Path, path: pathlib.Path) -> list[SourceTableRow]:
  rel = _rel(root, path)
  table = _table_name_from_source(root, path)
  rows: list[SourceTableRow] = []
  for line_no, raw_line in enumerate(_read_lines(path), start=1):
    line = raw_line.strip()
    if not line:
      continue
    try:
      raw = json.loads(line)
    except json.JSONDecodeError as exc:
      raise KbError(f"{rel}:{line_no}: invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
      raise KbError(f"{rel}:{line_no}: table row must be a JSON object")
    if "table" in raw and raw["table"] != table:
      raise KbError(f"{rel}:{line_no}: table field must match filename table `{table}`")
    row = dict(raw)
    row.pop("table", None)
    rows.append(SourceTableRow(table=table, payload=row, source=rel, line=line_no))
  return rows


def _shard_name(source_rel: str) -> str:
  digest = hashlib.sha256(source_rel.encode("utf-8")).hexdigest()[:16]
  return f"{digest}.jsonl"


def _compile_source(
    root: pathlib.Path,
    path: pathlib.Path,
    source_hash: str,
    known_skills: set[str],
) -> tuple[dict[str, object], str]:
  facts = _parse_source_file(root, path, known_skills)
  source_rel = _rel(root, path)
  payload = [fact.to_json() for fact in facts]
  text = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in payload)
  meta = {
    "source": source_rel,
    "source_hash": source_hash,
    "shard": _shard_name(source_rel),
    "fact_count": len(facts),
    "ids": sorted(fact.id for fact in facts),
    "skills": sorted({skill for fact in facts for skill in fact.skills}),
    "path_prefixes": sorted({prefix for fact in facts for prefix in fact.prefixes}),
  }
  return meta, text


def _compile_table_source(
    root: pathlib.Path,
    path: pathlib.Path,
    source_hash: str,
) -> tuple[dict[str, object], str]:
  rows = _parse_table_source(root, path)
  source_rel = _rel(root, path)
  table = _table_name_from_source(root, path)
  payload = [row.to_json() for row in rows]
  text = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in payload)
  meta = {
    "kind": "table",
    "table": table,
    "source": source_rel,
    "source_hash": source_hash,
    "shard": _shard_name(source_rel),
    "row_count": len(rows),
    "ids": sorted(
      str(row.payload["id"])
      for row in rows
      if isinstance(row.payload.get("id"), str)
    ),
  }
  return meta, text


def _load_manifest(root: pathlib.Path) -> dict[str, object] | None:
  manifest = _read_json(_manifest_path(root))
  if manifest is None:
    return None
  if manifest.get("schema_version") != SCHEMA_VERSION:
    return None
  return manifest


def cache_needs_rebuild(root: str | pathlib.Path | None = None) -> bool:
  repo_root = _repo_root(root)
  manifest = _load_manifest(repo_root)
  if manifest is None:
    return True
  meta_map = {
    entry["source"]: entry
    for entry in manifest.get("sources", [])
    if isinstance(entry, dict) and isinstance(entry.get("source"), str)
  }
  sources = _discover_sources(repo_root)
  table_sources = _discover_table_sources(repo_root)
  all_sources = sources + table_sources
  if set(meta_map) != {_rel(repo_root, path) for path in all_sources}:
    return True
  for path in all_sources:
    rel = _rel(repo_root, path)
    entry = meta_map.get(rel)
    if not isinstance(entry, dict):
      return True
    if entry.get("source_hash") != _hash_file(path):
      return True
    shard = entry.get("shard")
    if not isinstance(shard, str) or not (_shards_dir(repo_root) / shard).is_file():
      return True
  return False


def rebuild_cache(
    root: str | pathlib.Path | None = None,
    *,
    force: bool = False,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  sources = _discover_sources(repo_root)
  table_sources = _discover_table_sources(repo_root)
  known_skills = _known_skills(repo_root)
  old_manifest = _load_manifest(repo_root) or {"sources": []}
  old_meta = {
    entry["source"]: entry
    for entry in old_manifest.get("sources", [])
    if isinstance(entry, dict) and isinstance(entry.get("source"), str)
  }
  hashes = {path: _hash_file(path) for path in sources + table_sources}

  reused: list[dict[str, object]] = []
  to_build: list[tuple[pathlib.Path, str]] = []
  for path in sources + table_sources:
    rel = _rel(repo_root, path)
    old = old_meta.get(rel)
    shard_ok = isinstance(old, dict) and isinstance(old.get("shard"), str) and (
      _shards_dir(repo_root) / str(old["shard"])
    ).is_file()
    if (
      not force
      and isinstance(old, dict)
      and old.get("source_hash") == hashes[path]
      and shard_ok
    ):
      reused.append(old)
      continue
    to_build.append((path, hashes[path]))

  built_meta: list[dict[str, object]] = []
  written = 0
  if to_build:
    workers = min(len(to_build), os.cpu_count() or 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
      futs = [
        (
          pool.submit(_compile_source, repo_root, path, source_hash, known_skills)
          if path in sources else
          pool.submit(_compile_table_source, repo_root, path, source_hash)
        )
        for path, source_hash in to_build
      ]
      for fut in concurrent.futures.as_completed(futs):
        meta, text = fut.result()
        shard_name = str(meta["shard"])
        shard_path = _shards_dir(repo_root) / shard_name
        if _write_text_if_changed(shard_path, text):
          written += 1
        built_meta.append(meta)

  final_meta = sorted(reused + built_meta, key=lambda entry: str(entry["source"]))
  seen_ids: dict[str, str] = {}
  for meta in final_meta:
    if meta.get("kind") == "table":
      continue
    for fact_id in meta.get("ids", []):
      if not isinstance(fact_id, str):
        continue
      owner = seen_ids.get(fact_id)
      if owner is not None and owner != meta["source"]:
        raise KbError(
          f"duplicate fact id `{fact_id}` in {owner} and {meta['source']}"
        )
      seen_ids[fact_id] = str(meta["source"])

  active_shards = {
    str(entry["shard"])
    for entry in final_meta
    if isinstance(entry.get("shard"), str)
  }
  removed_shards = 0
  shards_dir = _shards_dir(repo_root)
  if shards_dir.is_dir():
    for shard in shards_dir.glob("*.jsonl"):
      if shard.name not in active_shards:
        shard.unlink()
        removed_shards += 1

  manifest_payload = {
    "schema_version": SCHEMA_VERSION,
    "sources": final_meta,
  }
  manifest_written = _write_text_if_changed(
    _manifest_path(repo_root), _json_text(manifest_payload)
  )
  return {
    "sources": len(sources) + len(table_sources),
    "rebuilt_sources": len(to_build),
    "reused_sources": len(reused),
    "written_shards": written,
    "removed_shards": removed_shards,
    "manifest_written": manifest_written,
  }


def _load_compiled_facts(root: pathlib.Path, shard_names: list[str]) -> list[CompiledFact]:
  out: list[CompiledFact] = []
  for shard_name in shard_names:
    shard_path = _shards_dir(root) / shard_name
    for line in _read_lines(shard_path):
      raw = json.loads(line)
      out.append(
        CompiledFact(
          id=str(raw["id"]),
          says=tuple(raw.get("says", [])),
          paths=tuple(raw.get("paths", [])),
          verbs=tuple(raw.get("verbs", [])),
          phases=tuple(raw.get("phases", [])),
          skills=tuple(raw.get("skills", [])),
          refs=tuple(raw.get("refs", [])),
          checks=tuple(raw.get("checks", [])),
          read_next=tuple(raw.get("read_next", [])),
          priority=int(raw.get("priority", 0)),
          prefixes=tuple(raw.get("prefixes", [])),
          source=str(raw["source"]),
          line=int(raw["line"]),
        )
      )
  return out


def _shortlist_shards(
    sources: list[dict[str, object]], paths: tuple[str, ...]
) -> list[str]:
  if not paths:
    return [
      str(entry["shard"])
      for entry in sources
      if isinstance(entry.get("shard"), str)
    ]
  out: list[str] = []
  for entry in sources:
    shard = entry.get("shard")
    prefixes = entry.get("path_prefixes", [])
    if not isinstance(shard, str):
      continue
    if not isinstance(prefixes, list):
      continue
    if any(
      prefix == ""
      or path == prefix
      or path.startswith(prefix)
      for prefix in prefixes
      if isinstance(prefix, str)
      for path in paths
    ):
      out.append(shard)
  return sorted(set(out))


def ensure_cache(root: str | pathlib.Path | None = None) -> None:
  repo_root = _repo_root(root)
  if cache_needs_rebuild(repo_root):
    rebuild_cache(repo_root)


def probe(
    root: str | pathlib.Path | None = None,
    *,
    paths: list[str] | None = None,
    verb: str | None = None,
    phase: str | None = None,
    claims: list[str] | None = None,
) -> ProbeResult:
  repo_root = _repo_root(root)
  ensure_cache(repo_root)
  manifest = _load_manifest(repo_root)
  if manifest is None:
    raise KbError("agent KB cache missing after rebuild")
  norm_paths = tuple(sorted(set(paths or [])))
  shard_names = _shortlist_shards(
    [
      entry for entry in manifest.get("sources", [])
      if isinstance(entry, dict)
    ],
    norm_paths,
  )
  facts = [
    fact
    for fact in _load_compiled_facts(repo_root, shard_names)
    if _fact_matches(fact, paths=norm_paths, verb=verb, phase=phase)
  ]
  facts.sort(key=lambda fact: _score_fact(fact, norm_paths), reverse=True)
  skills = sorted({skill for fact in facts for skill in fact.skills})
  claim_set = set(claims or [])
  checks = sorted({check for fact in facts for check in fact.checks})
  refs = sorted({ref for fact in facts for ref in fact.refs})
  read_next = sorted({ref for fact in facts for ref in fact.read_next})
  return ProbeResult(
    facts=tuple(facts),
    skills=tuple(skills),
    missing_skills=tuple(skill for skill in skills if skill not in claim_set),
    checks=tuple(checks),
    refs=tuple(refs),
    read_next=tuple(read_next),
    scanned_shards=tuple(shard_names),
  )


def read_fact(
    fact_id: str,
    root: str | pathlib.Path | None = None,
) -> CompiledFact:
  repo_root = _repo_root(root)
  ensure_cache(repo_root)
  manifest = _load_manifest(repo_root)
  if manifest is None:
    raise KbError("agent KB cache missing after rebuild")
  shard_names = []
  for entry in manifest.get("sources", []):
    if not isinstance(entry, dict):
      continue
    ids = entry.get("ids", [])
    if isinstance(ids, list) and fact_id in ids and isinstance(entry.get("shard"), str):
      shard_names.append(str(entry["shard"]))
  if not shard_names:
    raise KbError(f"fact not found: {fact_id}")
  for fact in _load_compiled_facts(repo_root, shard_names):
    if fact.id == fact_id:
      return fact
  raise KbError(f"fact not found: {fact_id}")


def _valid_table_name(table: str) -> bool:
  return (
    bool(table)
    and table[0].isalpha()
    and all(ch.isalnum() or ch in {"_", "-"} for ch in table)
  )


def _runtime_table_path(root: pathlib.Path, table: str) -> pathlib.Path:
  if not _valid_table_name(table):
    raise KbError(f"invalid table name: {table}")
  return _runtime_dir(root) / f"{table}.jsonl"


def _parse_scalar(raw: str) -> object:
  try:
    return json.loads(raw)
  except json.JSONDecodeError:
    return raw


def _parse_pairs(pairs: list[str]) -> dict[str, object]:
  out: dict[str, object] = {}
  for pair in pairs:
    key, sep, raw_val = pair.partition("=")
    if not sep or not key:
      raise KbError(f"invalid key=value pair: {pair}")
    out[key] = _parse_scalar(raw_val)
  return out


def _load_runtime_rows(root: pathlib.Path, table: str) -> list[dict[str, object]]:
  path = _runtime_table_path(root, table)
  if not path.is_file():
    return []
  rows: list[dict[str, object]] = []
  for line_no, line in enumerate(_read_lines(path), start=1):
    text = line.strip()
    if not text:
      continue
    try:
      row = json.loads(text)
    except json.JSONDecodeError as exc:
      raise KbError(f"{_rel(root, path)}:{line_no}: invalid JSON: {exc.msg}") from exc
    if not isinstance(row, dict):
      raise KbError(f"{_rel(root, path)}:{line_no}: row must be a JSON object")
    rows.append(row)
  return rows


def _write_runtime_rows(
    root: pathlib.Path,
    table: str,
    rows: list[dict[str, object]],
) -> bool:
  path = _runtime_table_path(root, table)
  if not rows:
    if path.exists():
      path.unlink()
      return True
    return False
  text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
  return _write_text_if_changed(path, text)


def _append_runtime_row(
    root: pathlib.Path,
    table: str,
    row: dict[str, object],
) -> None:
  path = _runtime_table_path(root, table)
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(row, sort_keys=True) + "\n")


def _all_fact_rows(root: pathlib.Path) -> list[dict[str, object]]:
  ensure_cache(root)
  manifest = _load_manifest(root)
  if manifest is None:
    raise KbError("agent KB cache missing after rebuild")
  shard_names = [
    str(entry["shard"])
    for entry in manifest.get("sources", [])
    if isinstance(entry, dict)
    and entry.get("kind") != "table"
    and isinstance(entry.get("shard"), str)
  ]
  return [
    {"table": "facts", **fact.to_json()}
    for fact in _load_compiled_facts(root, shard_names)
  ]


def _table_rows(root: pathlib.Path, table: str) -> list[dict[str, object]]:
  if table == "facts":
    return _all_fact_rows(root)
  ensure_cache(root)
  manifest = _load_manifest(root)
  rows: list[dict[str, object]] = []
  if manifest is not None:
    for entry in manifest.get("sources", []):
      if not isinstance(entry, dict):
        continue
      if entry.get("kind") != "table" or entry.get("table") != table:
        continue
      shard = entry.get("shard")
      if not isinstance(shard, str):
        continue
      shard_path = _shards_dir(root) / shard
      for line in _read_lines(shard_path):
        row = json.loads(line)
        if isinstance(row, dict):
          rows.append(row)
  rows.extend({"table": table, **row} for row in _load_runtime_rows(root, table))
  return rows


def _row_matches(row: dict[str, object], filters: dict[str, object]) -> bool:
  for key, expected in filters.items():
    actual = row.get(key)
    if actual == expected:
      continue
    if isinstance(actual, list) and expected in actual:
      continue
    return False
  return True


def query_table(
    root: str | pathlib.Path | None,
    table: str,
    *,
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  rows = _table_rows(repo_root, table)
  want = filters or {}
  matched = [row for row in rows if _row_matches(row, want)]
  return {
    "table": table,
    "filters": want,
    "row_count": len(matched),
    "rows": matched,
  }


def query_request_brief(
    root: str | pathlib.Path | None,
    request_id: str,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  payload = query_table(repo_root, "requests", filters={"id": request_id})
  rows = payload["rows"]
  if not isinstance(rows, list) or not rows:
    raise KbError(f"request not found: {request_id}")
  req = rows[-1]
  paths: list[str] = []
  path = req.get("path")
  if isinstance(path, str) and path:
    paths.append(path)
  many_paths = req.get("paths")
  if isinstance(many_paths, list):
    paths.extend(p for p in many_paths if isinstance(p, str))
  claims_raw = req.get("claims")
  claims = [c for c in claims_raw if isinstance(c, str)] if isinstance(claims_raw, list) else []
  if isinstance(req.get("claim"), str):
    claims.append(str(req["claim"]))
  verb = req.get("verb") if isinstance(req.get("verb"), str) else None
  phase = req.get("phase") if isinstance(req.get("phase"), str) else None
  briefing = probe(repo_root, paths=paths, verb=verb, phase=phase, claims=claims)
  return {
    "request": req,
    "briefing": briefing.to_json(),
  }


def query_backlog(
    root: str | pathlib.Path | None,
    *,
    area: str | None = None,
    priority: str | None = None,
    path: str | None = None,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  payload = query_table(
    repo_root,
    "backlog",
    filters={k: v for k, v in {"area": area, "priority": priority}.items() if v is not None},
  )
  rows = []
  for row in payload["rows"]:
    if not isinstance(row, dict):
      continue
    if path:
      many_paths = row.get("paths", [])
      row_path = row.get("path")
      path_values = []
      if isinstance(row_path, str):
        path_values.append(row_path)
      if isinstance(many_paths, list):
        path_values.extend(p for p in many_paths if isinstance(p, str))
      if path_values and not any(glob_match(path, candidate) or glob_match(candidate, path) for candidate in path_values):
        continue
    rows.append(row)
  return {
    "filters": {"area": area, "priority": priority, "path": path},
    "row_count": len(rows),
    "rows": rows,
  }


def _row_paths(row: dict[str, object]) -> list[str]:
  paths: list[str] = []
  row_path = row.get("path")
  if isinstance(row_path, str) and row_path:
    paths.append(row_path)
  many_paths = row.get("paths")
  if isinstance(many_paths, list):
    paths.extend(path for path in many_paths if isinstance(path, str) and path)
  return paths


def _numeric_feedback(value: object) -> float | None:
  if isinstance(value, bool):
    return None
  if isinstance(value, (int, float)):
    return float(value)
  return None


def _feedback_used(row: dict[str, object]) -> bool | None:
  used = row.get("used")
  if isinstance(used, bool):
    return used
  usefulness = _numeric_feedback(row.get("usefulness"))
  if usefulness is not None and usefulness != 0:
    return True
  return None


def _feedback_sentiment(row: dict[str, object]) -> int:
  usefulness = _numeric_feedback(row.get("usefulness"))
  if usefulness is not None:
    if usefulness > 0:
      return 1
    if usefulness < 0:
      return -1
    return 0
  outcome = row.get("outcome")
  if not isinstance(outcome, str):
    return 0
  normalized = outcome.strip().lower()
  if normalized in {"high-value", "helpful", "essential", "selected"}:
    return 1
  if normalized in {"low-value", "harmful", "waste"}:
    return -1
  return 0


def _feedback_matches_scope(
    row: dict[str, object],
    *,
    area: str | None,
    priority: str | None,
    path: str | None,
    problem_id: str | None,
    tool_id: str | None = None,
) -> bool:
  if tool_id is not None and row.get("tool_id") != tool_id:
    return False
  if problem_id is not None:
    row_problem = row.get("problem_id")
    if isinstance(row_problem, str) and row_problem and row_problem != problem_id:
      return False
  if area is not None:
    row_area = row.get("area")
    if isinstance(row_area, str) and row_area and row_area != area:
      return False
  if priority is not None:
    row_priority = row.get("priority")
    if isinstance(row_priority, str) and row_priority and row_priority != priority:
      return False
  if path is not None:
    row_paths = _row_paths(row)
    if row_paths and not any(
      glob_match(path, candidate) or glob_match(candidate, path)
      for candidate in row_paths
    ):
      return False
  return True


def _matching_tool_feedback(
    root: pathlib.Path,
    *,
    area: str | None,
    priority: str | None,
    path: str | None,
    problem_id: str | None,
    tool_id: str | None = None,
) -> list[dict[str, object]]:
  run_rows = query_table(root, "solver_runs")["rows"]
  runs_by_id = {
    str(row["id"]): row
    for row in run_rows
    if isinstance(row, dict) and isinstance(row.get("id"), str)
  }
  matched: list[dict[str, object]] = []
  for row in query_table(root, "tool_feedback")["rows"]:
    if not isinstance(row, dict):
      continue
    merged = dict(row)
    run_id = row.get("run_id")
    if isinstance(run_id, str):
      solver_run = runs_by_id.get(run_id)
      if solver_run is not None:
        merged["solver_run"] = solver_run
        for key in (
          "goal",
          "area",
          "priority",
          "path",
          "paths",
          "problem_id",
          "phase",
          "status",
        ):
          if key not in merged and key in solver_run:
            merged[key] = solver_run[key]
    if not _feedback_matches_scope(
      merged,
      area=area,
      priority=priority,
      path=path,
      problem_id=problem_id,
      tool_id=tool_id,
    ):
      continue
    matched.append(merged)
  return matched


def _summarize_feedback_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
  stats_by_tool: dict[str, dict[str, object]] = {}
  for row in rows:
    tool_id = row.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id:
      continue
    stats = stats_by_tool.setdefault(
      tool_id,
      {
        "tool_id": tool_id,
        "row_count": 0,
        "used_count": 0,
        "unused_count": 0,
        "positive_count": 0,
        "negative_count": 0,
        "scored_count": 0,
        "total_usefulness": 0.0,
        "outcomes": [],
        "problem_ids": [],
        "run_ids": [],
      },
    )
    stats["row_count"] = int(stats["row_count"]) + 1
    used = _feedback_used(row)
    if used is True:
      stats["used_count"] = int(stats["used_count"]) + 1
    elif used is False:
      stats["unused_count"] = int(stats["unused_count"]) + 1
    sentiment = _feedback_sentiment(row)
    if sentiment > 0:
      stats["positive_count"] = int(stats["positive_count"]) + 1
    elif sentiment < 0:
      stats["negative_count"] = int(stats["negative_count"]) + 1
    usefulness = _numeric_feedback(row.get("usefulness"))
    if usefulness is not None:
      stats["scored_count"] = int(stats["scored_count"]) + 1
      stats["total_usefulness"] = float(stats["total_usefulness"]) + usefulness
    outcome = row.get("outcome")
    if isinstance(outcome, str) and outcome not in stats["outcomes"]:
      stats["outcomes"].append(outcome)
    problem_id = row.get("problem_id")
    if isinstance(problem_id, str) and problem_id not in stats["problem_ids"]:
      stats["problem_ids"].append(problem_id)
    run_id = row.get("run_id")
    if isinstance(run_id, str) and run_id not in stats["run_ids"]:
      stats["run_ids"].append(run_id)

  summaries: list[dict[str, object]] = []
  for tool_id, stats in stats_by_tool.items():
    scored_count = int(stats["scored_count"])
    avg_usefulness = (
      float(stats["total_usefulness"]) / scored_count if scored_count else None
    )
    feedback_score = (
      int(stats["positive_count"]) * 25
      + int(stats["used_count"]) * 10
      - int(stats["negative_count"]) * 18
      - int(stats["unused_count"]) * 12
    )
    if avg_usefulness is not None:
      feedback_score += round(avg_usefulness * 5)
    summaries.append(
      {
        "tool_id": tool_id,
        "row_count": int(stats["row_count"]),
        "used_count": int(stats["used_count"]),
        "unused_count": int(stats["unused_count"]),
        "positive_count": int(stats["positive_count"]),
        "negative_count": int(stats["negative_count"]),
        "avg_usefulness": avg_usefulness,
        "feedback_score": feedback_score,
        "outcomes": list(stats["outcomes"]),
        "problem_ids": list(stats["problem_ids"]),
        "run_ids": list(stats["run_ids"]),
      }
    )
  summaries.sort(
    key=lambda row: (
      int(row["feedback_score"]),
      int(row["row_count"]),
      str(row["tool_id"]),
    ),
    reverse=True,
  )
  return summaries


def query_feedback_summary(
    root: str | pathlib.Path | None,
    *,
    area: str | None = None,
    priority: str | None = None,
    path: str | None = None,
    problem_id: str | None = None,
    tool_id: str | None = None,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  matched_rows = _matching_tool_feedback(
    repo_root,
    area=area,
    priority=priority,
    path=path,
    problem_id=problem_id,
    tool_id=tool_id,
  )
  return {
    "filters": {
      "area": area,
      "priority": priority,
      "path": path,
      "problem_id": problem_id,
      "tool_id": tool_id,
    },
    "row_count": len(matched_rows),
    "rows": matched_rows,
    "tools": _summarize_feedback_rows(matched_rows),
  }


def query_recommend_tools(
    root: str | pathlib.Path | None,
    *,
    area: str | None = None,
    priority: str | None = None,
    path: str | None = None,
    problem_id: str | None = None,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  problem: dict[str, object] | None = None
  if problem_id:
    payload = query_table(repo_root, "backlog", filters={"id": problem_id})
    rows = payload["rows"]
    if not isinstance(rows, list) or not rows:
      payload = query_table(repo_root, "problems", filters={"id": problem_id})
      rows = payload["rows"]
    if not isinstance(rows, list) or not rows:
      raise KbError(f"problem not found: {problem_id}")
    problem = rows[-1]
    if area is None and isinstance(problem.get("area"), str):
      area = str(problem["area"])
    if priority is None and isinstance(problem.get("priority"), str):
      priority = str(problem["priority"])
    if path is None and isinstance(problem.get("path"), str):
      path = str(problem["path"])
    if path is None and isinstance(problem.get("paths"), list):
      for entry in problem["paths"]:
        if isinstance(entry, str):
          path = entry
          break

  tools_payload = query_table(repo_root, "tool_catalog")
  playbooks_payload = query_table(repo_root, "tool_playbooks")
  playbooks = []
  tool_ids: list[str] = []
  static_scores: dict[str, int] = {}
  for row in playbooks_payload["rows"]:
    if not isinstance(row, dict):
      continue
    areas = row.get("areas", [])
    priorities = row.get("priorities", [])
    path_globs = row.get("paths", [])
    if area and isinstance(areas, list) and areas and area not in areas:
      continue
    if priority and isinstance(priorities, list) and priorities and priority not in priorities:
      continue
    if path and isinstance(path_globs, list) and path_globs:
      if not any(isinstance(glob, str) and glob_match(path, glob) for glob in path_globs):
        continue
    playbooks.append(row)
    ids = row.get("tool_ids", [])
    if isinstance(ids, list):
      for index, tool_id in enumerate(ids):
        if not isinstance(tool_id, str):
          continue
        tool_ids.append(tool_id)
        static_scores[tool_id] = static_scores.get(tool_id, 0) + max(1, 30 - index * 3)

  feedback = query_feedback_summary(
    repo_root,
    area=area,
    priority=priority,
    path=path,
    problem_id=problem_id,
  )
  feedback_by_tool = {
    str(row["tool_id"]): row
    for row in feedback["tools"]
    if isinstance(row, dict) and isinstance(row.get("tool_id"), str)
  }
  candidate_ids = list(dict.fromkeys([*tool_ids, *feedback_by_tool.keys()]))

  seen: set[str] = set()
  tools = []
  for row in tools_payload["rows"]:
    if not isinstance(row, dict):
      continue
    tool_id = row.get("id")
    if (
      not isinstance(tool_id, str)
      or tool_id not in candidate_ids
      or tool_id in seen
    ):
      continue
    seen.add(tool_id)
    tool = dict(row)
    static_score = static_scores.get(tool_id, 0)
    feedback_stats = feedback_by_tool.get(tool_id)
    feedback_score = 0
    reasons: list[str] = []
    if static_score:
      reasons.append(f"playbook score {static_score}")
    if isinstance(feedback_stats, dict):
      feedback_score = int(feedback_stats.get("feedback_score", 0))
      row_count = int(feedback_stats.get("row_count", 0))
      used_count = int(feedback_stats.get("used_count", 0))
      positive_count = int(feedback_stats.get("positive_count", 0))
      unused_count = int(feedback_stats.get("unused_count", 0))
      reasons.append(f"{row_count} matching feedback rows")
      if used_count:
        reasons.append(f"used in {used_count} solver runs")
      if positive_count:
        reasons.append(f"{positive_count} positive outcomes")
      if unused_count:
        reasons.append(f"{unused_count} recommended-but-unused rows")
      tool["feedback"] = feedback_stats
    tool["recommendation_score"] = static_score + feedback_score
    tool["recommendation_reasons"] = reasons
    tools.append(tool)
  tools.sort(
    key=lambda row: (
      int(row.get("recommendation_score", 0)),
      str(row.get("id", "")),
    ),
    reverse=True,
  )
  return {
    "problem": problem,
    "filters": {"area": area, "priority": priority, "path": path},
    "playbooks": playbooks,
    "feedback": feedback,
    "tools": tools,
  }


def _looks_like_path(text: str) -> bool:
  return (
    "/" in text
    or text.endswith((".c", ".h", ".py", ".md", ".jsonl", ".sh"))
    or text.startswith(("src", "tools", ".agents", "bootstrap", ".github"))
  )


def _flatten_text(value: object) -> list[str]:
  if isinstance(value, str):
    return [value]
  if isinstance(value, list):
    out: list[str] = []
    for item in value:
      out.extend(_flatten_text(item))
    return out
  if isinstance(value, dict):
    out: list[str] = []
    for item in value.values():
      out.extend(_flatten_text(item))
    return out
  return [str(value)] if value is not None else []


def _text_match_reasons(row: dict[str, object], terms: list[str]) -> list[str]:
  haystack = " ".join(part.lower() for part in _flatten_text(row))
  reasons: list[str] = []
  for term in terms:
    if term.lower() in haystack:
      reasons.append(term)
  return reasons


def _hint(
    *,
    kind: str,
    ident: str,
    summary: str,
    query_used: str,
    source_table: str,
    confidence: str,
    why_matched: list[str],
    score: int,
    skill: str | None = None,
    data: dict[str, object] | None = None,
) -> dict[str, object]:
  payload = {
    "kind": kind,
    "id": ident,
    "summary": summary,
    "score": score,
    "tags": {
      "query_used": query_used,
      "source_table": source_table,
      "confidence": confidence,
      "why_matched": why_matched,
    },
  }
  if skill:
    payload["tags"]["skill"] = skill
  if data is not None:
    payload["data"] = data
  return payload


def query_think(
    root: str | pathlib.Path | None,
    *,
    subjects: list[str] | None = None,
    verbs: list[str] | None = None,
    objects: list[str] | None = None,
    phase: str | None = None,
    claims: list[str] | None = None,
    limit: int = 12,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  subject_terms = [term for term in (subjects or []) if term]
  verb_terms = [term for term in (verbs or []) if term]
  object_terms = [term for term in (objects or []) if term]
  text_terms = [*subject_terms, *verb_terms, *object_terms]
  path_terms = [term for term in [*subject_terms, *object_terms] if _looks_like_path(term)]

  backlog_rows = query_backlog(
    repo_root,
    area=next((term for term in subject_terms if term in {"runtime-perf", "compile-perf", "architecture"}), None),
    path=path_terms[0] if path_terms else None,
  )["rows"]
  matched_backlog = [
    row for row in backlog_rows
    if isinstance(row, dict) and (_text_match_reasons(row, text_terms) or not text_terms)
  ]

  hints: list[dict[str, object]] = []
  seen: set[tuple[str, str, str]] = set()

  if path_terms:
    probe_result = probe(
      repo_root,
      paths=path_terms,
      verb=verb_terms[0] if verb_terms else None,
      phase=phase,
      claims=claims,
    )
    if not probe_result.facts and verb_terms:
      probe_result = probe(
        repo_root,
        paths=path_terms,
        verb=None,
        phase=phase,
        claims=claims,
      )
    for fact in probe_result.facts:
      why = [*path_terms]
      if verb_terms:
        why.extend(verb_terms[:1])
      key = ("fact", fact.id, "probe")
      if key in seen:
        continue
      seen.add(key)
      hints.append(
        _hint(
          kind="fact",
          ident=fact.id,
          summary=fact.says[0],
          query_used="probe",
          source_table="facts",
          confidence="high",
          why_matched=why,
          score=90 + fact.priority,
          skill=fact.skills[0] if fact.skills else None,
          data=fact.to_json(),
        )
      )
  else:
    fact_rows = query_table(repo_root, "facts")["rows"]
    for row in fact_rows:
      if not isinstance(row, dict):
        continue
      why = _text_match_reasons(row, text_terms)
      if not why:
        continue
      ident = str(row.get("id"))
      key = ("fact", ident, "table")
      if key in seen:
        continue
      seen.add(key)
      summary = next(iter(row.get("says", []) or [ident]), ident)
      skill = None
      if isinstance(row.get("skills"), list) and row["skills"]:
        first = row["skills"][0]
        if isinstance(first, str):
          skill = first
      hints.append(
        _hint(
          kind="fact",
          ident=ident,
          summary=str(summary),
          query_used="table",
          source_table="facts",
          confidence="medium",
          why_matched=why,
          score=80,
          skill=skill,
          data=row,
        )
      )

  for row in matched_backlog:
    ident = str(row.get("id"))
    key = ("backlog", ident, "backlog")
    if key in seen:
      continue
    seen.add(key)
    why = _text_match_reasons(row, text_terms) or path_terms or subject_terms or object_terms
    hints.append(
      _hint(
        kind="backlog",
        ident=ident,
        summary=str(row.get("title", ident)),
        query_used="backlog",
        source_table="backlog",
        confidence="high",
        why_matched=why,
        score=95,
        data=row,
      )
    )

  req_rows = query_table(repo_root, "requests")["rows"]
  for row in req_rows:
    if not isinstance(row, dict):
      continue
    why = _text_match_reasons(row, text_terms)
    if path_terms:
      row_paths = [p for p in row.get("paths", []) if isinstance(p, str)] if isinstance(row.get("paths"), list) else []
      if isinstance(row.get("path"), str):
        row_paths.append(str(row["path"]))
      if any(any(glob_match(rp, pt) or glob_match(pt, rp) for rp in row_paths) for pt in path_terms):
        why.extend(path_terms)
    if not why:
      continue
    ident = str(row.get("id"))
    key = ("request", ident, "table")
    if key in seen:
      continue
    seen.add(key)
    hints.append(
      _hint(
        kind="request",
        ident=ident,
        summary=f"request for {row.get('path', row.get('backlog_id', ident))}",
        query_used="table",
        source_table="requests",
        confidence="low",
        why_matched=sorted(set(why)),
        score=40,
        data=row,
      )
    )

  recommend_payloads = []
  if matched_backlog:
    for row in matched_backlog[:3]:
      if isinstance(row.get("id"), str):
        recommend_payloads.append(
          query_recommend_tools(repo_root, problem_id=str(row["id"]))
        )
  else:
    recommend_payloads.append(
      query_recommend_tools(
        repo_root,
        area=next((term for term in subject_terms if term in {"runtime-perf", "compile-perf", "architecture"}), None),
        path=path_terms[0] if path_terms else None,
      )
    )

  for payload in recommend_payloads:
    for row in payload.get("playbooks", []):
      if not isinstance(row, dict):
        continue
      ident = str(row.get("id"))
      key = ("playbook", ident, "recommend-tools")
      if key in seen:
        continue
      seen.add(key)
      why = _text_match_reasons(row, text_terms) or subject_terms or object_terms
      hints.append(
        _hint(
          kind="playbook",
          ident=ident,
          summary=str(row.get("why", ident)),
          query_used="recommend-tools",
          source_table="tool_playbooks",
          confidence="medium",
          why_matched=why,
          score=55,
          data=row,
        )
      )
    for row in payload.get("tools", []):
      if not isinstance(row, dict):
        continue
      ident = str(row.get("id"))
      key = ("tool", ident, "recommend-tools")
      if key in seen:
        continue
      seen.add(key)
      why = _text_match_reasons(row, text_terms) or subject_terms or object_terms
      hints.append(
        _hint(
          kind="tool",
          ident=ident,
          summary=str(row.get("name", ident)),
          query_used="recommend-tools",
          source_table="tool_catalog",
          confidence="medium",
          why_matched=why,
          score=int(row.get("recommendation_score", 60)),
          data=row,
        )
      )

  hints.sort(key=lambda hint: (int(hint["score"]), str(hint["id"])), reverse=True)
  return {
    "inputs": {
      "subjects": subject_terms,
      "verbs": verb_terms,
      "objects": object_terms,
      "phase": phase,
      "claims": claims or [],
    },
    "results": hints[:limit],
  }


def action_table(
    root: str | pathlib.Path | None,
    table: str,
    verb: str,
    *,
    row_id: str | None = None,
    fields: dict[str, object] | None = None,
) -> dict[str, object]:
  repo_root = _repo_root(root)
  if table == "facts":
    raise KbError("facts table is compiled repo-state; use rebuild, not action")
  payload = dict(fields or {})
  if row_id is not None:
    payload["id"] = row_id
  if verb == "insert":
    _append_runtime_row(repo_root, table, payload)
    return {"table": table, "verb": verb, "written": 1}
  rows = _load_runtime_rows(repo_root, table)
  if verb == "clear":
    changed = _write_runtime_rows(repo_root, table, [])
    return {"table": table, "verb": verb, "written": 0, "changed": changed}
  if row_id is None:
    raise KbError(f"{verb} requires --id")
  if verb == "delete":
    kept = [row for row in rows if row.get("id") != row_id]
    removed = len(rows) - len(kept)
    changed = _write_runtime_rows(repo_root, table, kept)
    return {
      "table": table,
      "verb": verb,
      "removed": removed,
      "changed": changed,
    }
  if verb == "upsert":
    kept = [row for row in rows if row.get("id") != row_id]
    kept.append(payload)
    changed = _write_runtime_rows(repo_root, table, kept)
    return {
      "table": table,
      "verb": verb,
      "written": 1,
      "changed": changed,
    }
  raise KbError(f"unknown action verb: {verb}")


def stale_issues(root: str | pathlib.Path | None = None) -> list[str]:
  repo_root = _repo_root(root)
  issues: list[str] = []
  manifest = _load_manifest(repo_root)
  if manifest is None:
    issues.append("cache missing or schema version changed")
  elif cache_needs_rebuild(repo_root):
    issues.append("cache stale vs source hashes")

  known_skills = _known_skills(repo_root)
  seen_ids: dict[str, str] = {}
  for path in _discover_sources(repo_root):
    try:
      facts = _parse_source_file(repo_root, path, known_skills)
    except KbError as exc:
      issues.append(str(exc))
      continue
    rel = _rel(repo_root, path)
    for fact in facts:
      owner = seen_ids.get(fact.id)
      if owner is not None and owner != rel:
        issues.append(f"duplicate fact id `{fact.id}` in {owner} and {rel}")
      else:
        seen_ids[fact.id] = rel
  return sorted(set(issues))


def _render_fact(fact: CompiledFact) -> str:
  out = [f"{fact.id} ({fact.source}:{fact.line})"]
  out.extend(f"  - {line}" for line in fact.says)
  if fact.skills:
    out.append(f"  skills: {', '.join(fact.skills)}")
  if fact.refs:
    out.append(f"  refs: {', '.join(fact.refs)}")
  if fact.checks:
    out.append(f"  checks: {', '.join(fact.checks)}")
  if fact.read_next:
    out.append(f"  read next: {', '.join(fact.read_next)}")
  return "\n".join(out)


def _render_probe(result: ProbeResult) -> str:
  parts = ["agent probe"]
  parts.append(f"skills: {', '.join(result.skills) if result.skills else 'none'}")
  parts.append(
    "missing skills: "
    f"{', '.join(result.missing_skills) if result.missing_skills else 'none'}"
  )
  parts.append(f"checks: {', '.join(result.checks) if result.checks else 'none'}")
  parts.append(f"refs: {', '.join(result.refs) if result.refs else 'none'}")
  parts.append(
    "read next: "
    f"{', '.join(result.read_next) if result.read_next else 'none'}"
  )
  parts.append(
    "scanned shards: "
    f"{', '.join(result.scanned_shards) if result.scanned_shards else 'none'}"
  )
  parts.append("facts:")
  if not result.facts:
    parts.append("  - none")
  else:
    parts.extend(f"  - {fact.id}: {fact.says[0]}" for fact in result.facts)
  return "\n".join(parts) + "\n"


def _render_stale(issues: list[str]) -> str:
  parts = ["agent stale", "issues:"]
  if not issues:
    parts.append("  - none")
  else:
    parts.extend(f"  - {issue}" for issue in issues)
  return "\n".join(parts) + "\n"


def _render_backlog(payload: dict[str, object]) -> str:
  rows = payload.get("rows", [])
  out = ["agent backlog"]
  if not isinstance(rows, list) or not rows:
    out.append("  - none")
    return "\n".join(out) + "\n"
  grouped: dict[str, list[dict[str, object]]] = {}
  for row in rows:
    if not isinstance(row, dict):
      continue
    key = f"{row.get('area', 'unknown')} / {row.get('priority', '?')}"
    grouped.setdefault(key, []).append(row)
  for key in sorted(grouped):
    out.append(key)
    for row in sorted(grouped[key], key=lambda entry: str(entry.get("id", ""))):
      path = ""
      if isinstance(row.get("path"), str):
        path = str(row["path"])
      elif isinstance(row.get("paths"), list):
        for entry in row["paths"]:
          if isinstance(entry, str):
            path = entry
            break
      suffix = f" ({path})" if path else ""
      out.append(f"  - {row.get('id')}: {row.get('title')}{suffix}")
  return "\n".join(out) + "\n"


def _render_think(payload: dict[str, object]) -> str:
  results = payload.get("results", [])
  out = ["agent think"]
  if not isinstance(results, list) or not results:
    out.append("  - none")
    return "\n".join(out) + "\n"
  for row in results:
    if not isinstance(row, dict):
      continue
    tags = row.get("tags", {})
    query_used = tags.get("query_used") if isinstance(tags, dict) else None
    source_table = tags.get("source_table") if isinstance(tags, dict) else None
    why = tags.get("why_matched") if isinstance(tags, dict) else None
    suffix = f" [{query_used}/{source_table}]" if query_used and source_table else ""
    out.append(f"  - {row.get('kind')}:{row.get('id')} — {row.get('summary')}{suffix}")
    if isinstance(why, list) and why:
      out.append(f"      why: {', '.join(str(v) for v in why)}")
  return "\n".join(out) + "\n"


def _rewrite_frontdoor(argv: list[str] | None) -> list[str] | None:
  if not argv:
    return argv
  out = list(argv)
  if "--query" in out:
    idx = out.index("--query")
    return out[:idx] + ["query"] + out[idx + 1:]
  if "--action" in out:
    idx = out.index("--action")
    return out[:idx] + ["action"] + out[idx + 1:]
  return out


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="agent")
  parser.add_argument(
    "--root",
    default=os.environ.get("REPO_ROOT") or os.getcwd(),
    help="Repository root (defaults to REPO_ROOT or cwd).",
  )
  sub = parser.add_subparsers(dest="cmd", required=True)

  p_probe = sub.add_parser(
    "probe",
    help="Resolve active KB facts for a path/task scope.",
  )
  p_probe.add_argument("--path", action="append", default=[], dest="paths")
  p_probe.add_argument("--verb")
  p_probe.add_argument("--phase")
  p_probe.add_argument("--claim", action="append", default=[], dest="claims")
  p_probe.add_argument("--json", action="store_true")

  p_read = sub.add_parser("read", help="Print one KB fact by id.")
  p_read.add_argument("fact_id")
  p_read.add_argument("--json", action="store_true")

  p_rebuild = sub.add_parser("rebuild", help="Rebuild sharded KB cache.")
  p_rebuild.add_argument("--force", action="store_true")
  p_rebuild.add_argument("--json", action="store_true")

  p_stale = sub.add_parser("stale", help="Check KB source/cache issues.")
  p_stale.add_argument("--json", action="store_true")

  p_query = sub.add_parser(
    "query",
    help="Run a named query over cached repo-state/runtime tables.",
  )
  qsub = p_query.add_subparsers(dest="query_name", required=True)

  q_probe = qsub.add_parser("probe", help="Resolve active guidance for a scope.")
  q_probe.add_argument("--path", action="append", default=[], dest="paths")
  q_probe.add_argument("--verb")
  q_probe.add_argument("--phase")
  q_probe.add_argument("--claim", action="append", default=[], dest="claims")
  q_probe.add_argument("--json", action="store_true")

  q_fact = qsub.add_parser("fact", help="Read one fact row by id.")
  q_fact.add_argument("fact_id")
  q_fact.add_argument("--json", action="store_true")

  q_table = qsub.add_parser("table", help="Dump one table with optional filters.")
  q_table.add_argument("table")
  q_table.add_argument("--where", action="append", default=[])
  q_table.add_argument("--json", action="store_true")

  q_req = qsub.add_parser(
    "request-brief",
    help="Join one request row with matched facts and return briefing.",
  )
  q_req.add_argument("request_id")
  q_req.add_argument("--json", action="store_true")

  q_backlog = qsub.add_parser(
    "backlog",
    help="List backlog items with human-friendly output by default.",
  )
  q_backlog.add_argument("--area")
  q_backlog.add_argument("--priority")
  q_backlog.add_argument("--path")
  q_backlog.add_argument("--json", action="store_true")

  q_think = qsub.add_parser(
    "think",
    help="Synthesize helpful tagged info from multiple underlying queries.",
  )
  q_think.add_argument("--subject", action="append", default=[], dest="subjects")
  q_think.add_argument("--verb", action="append", default=[], dest="verbs")
  q_think.add_argument("--object", action="append", default=[], dest="objects")
  q_think.add_argument("--phase")
  q_think.add_argument("--claim", action="append", default=[], dest="claims")
  q_think.add_argument("--limit", type=int, default=12)
  q_think.add_argument("--json", action="store_true")

  q_tools = qsub.add_parser(
    "recommend-tools",
    help="Recommend common tools/playbooks for an area or runtime problem row.",
  )
  q_tools.add_argument("--area")
  q_tools.add_argument("--priority")
  q_tools.add_argument("--path")
  q_tools.add_argument("--problem-id")
  q_tools.add_argument("--json", action="store_true")

  q_feedback = qsub.add_parser(
    "feedback-summary",
    help="Summarize solver-run tool feedback for one problem or scope.",
  )
  q_feedback.add_argument("--area")
  q_feedback.add_argument("--priority")
  q_feedback.add_argument("--path")
  q_feedback.add_argument("--problem-id")
  q_feedback.add_argument("--tool-id")
  q_feedback.add_argument("--json", action="store_true")

  p_action = sub.add_parser(
    "action",
    help="Write or mutate one runtime table under build/agent-kb/runtime/.",
  )
  p_action.add_argument("table")
  p_action.add_argument("verb", choices=["insert", "upsert", "delete", "clear"])
  p_action.add_argument("--id", dest="row_id")
  p_action.add_argument("--set", action="append", default=[])
  p_action.add_argument(
    "--data",
    help="Full JSON object payload; merged after --set pairs.",
  )
  p_action.add_argument("--json", action="store_true")

  return parser


def main(argv: list[str] | None = None) -> int:
  if argv is None:
    argv = sys.argv[1:]
  argv = _rewrite_frontdoor(argv)
  parser = build_parser()
  args = parser.parse_args(argv)
  root = _repo_root(args.root)
  try:
    if args.cmd == "probe":
      result = probe(
        root,
        paths=args.paths,
        verb=args.verb,
        phase=args.phase,
        claims=args.claims,
      )
      if args.json:
        sys.stdout.write(_json_text(result.to_json()))
      else:
        sys.stdout.write(_render_probe(result))
      return 0
    if args.cmd == "read":
      fact = read_fact(args.fact_id, root)
      if args.json:
        sys.stdout.write(_json_text(fact.to_json()))
      else:
        sys.stdout.write(_render_fact(fact) + "\n")
      return 0
    if args.cmd == "rebuild":
      result = rebuild_cache(root, force=args.force)
      if args.json:
        sys.stdout.write(_json_text(result))
      else:
        sys.stdout.write(_json_text(result))
      return 0
    if args.cmd == "stale":
      issues = stale_issues(root)
      if args.json:
        sys.stdout.write(_json_text({"issues": issues}))
      else:
        sys.stdout.write(_render_stale(issues))
      return 1 if issues else 0
    if args.cmd == "query":
      if args.query_name == "probe":
        result = probe(
          root,
          paths=args.paths,
          verb=args.verb,
          phase=args.phase,
          claims=args.claims,
        )
        payload = result.to_json()
        if args.json:
          sys.stdout.write(_json_text(payload))
        else:
          sys.stdout.write(_render_probe(result))
        return 0
      if args.query_name == "fact":
        fact = read_fact(args.fact_id, root)
        payload = {"table": "facts", **fact.to_json()}
        if args.json:
          sys.stdout.write(_json_text(payload))
        else:
          sys.stdout.write(_render_fact(fact) + "\n")
        return 0
      if args.query_name == "table":
        payload = query_table(root, args.table, filters=_parse_pairs(args.where))
        sys.stdout.write(_json_text(payload))
        return 0
      if args.query_name == "request-brief":
        payload = query_request_brief(root, args.request_id)
        sys.stdout.write(_json_text(payload))
        return 0
      if args.query_name == "backlog":
        payload = query_backlog(
          root,
          area=args.area,
          priority=args.priority,
          path=args.path,
        )
        if args.json:
          sys.stdout.write(_json_text(payload))
        else:
          sys.stdout.write(_render_backlog(payload))
        return 0
      if args.query_name == "think":
        payload = query_think(
          root,
          subjects=args.subjects,
          verbs=args.verbs,
          objects=args.objects,
          phase=args.phase,
          claims=args.claims,
          limit=args.limit,
        )
        if args.json:
          sys.stdout.write(_json_text(payload))
        else:
          sys.stdout.write(_render_think(payload))
        return 0
      if args.query_name == "recommend-tools":
        payload = query_recommend_tools(
          root,
          area=args.area,
          priority=args.priority,
          path=args.path,
          problem_id=args.problem_id,
        )
        sys.stdout.write(_json_text(payload))
        return 0
      if args.query_name == "feedback-summary":
        payload = query_feedback_summary(
          root,
          area=args.area,
          priority=args.priority,
          path=args.path,
          problem_id=args.problem_id,
          tool_id=args.tool_id,
        )
        sys.stdout.write(_json_text(payload))
        return 0
    if args.cmd == "action":
      fields = _parse_pairs(args.set)
      if args.data:
        try:
          raw = json.loads(args.data)
        except json.JSONDecodeError as exc:
          raise KbError(f"--data invalid JSON: {exc.msg}") from exc
        if not isinstance(raw, dict):
          raise KbError("--data must decode to a JSON object")
        fields.update(raw)
      payload = action_table(
        root,
        args.table,
        args.verb,
        row_id=args.row_id,
        fields=fields,
      )
      sys.stdout.write(_json_text(payload))
      return 0
  except KbError as exc:
    print(f"agent: {exc}", file=sys.stderr)
    return 1
  raise AssertionError(f"unhandled command: {args.cmd}")


if __name__ == "__main__":
  raise SystemExit(main())
