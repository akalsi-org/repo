"""Load + resolve personality definitions and `_defaults.yaml`.

The personality `_defaults.yaml` and the YAML front matter inside
`personality.md` are restricted to a small, statically-known shape — see
`docs/research/multi_cli_personality_skill_spec.md`. We hand-roll a
small parser that handles only that shape so the slice does not need
PyYAML.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any


PERSONALITIES_REL = ".agents/personalities"
DEFAULTS_REL = ".agents/personalities/_defaults.yaml"
SUPPORTED_CLIS = ("claude", "codex", "copilot")
ALLOWED_PERSONALITY_FIELDS = {
  "name", "title", "cli", "model", "effort", "mode", "delegates_to",
  "tools", "clear_policy",
}
ALLOWED_TOOLS_KEYS = {"shell_allowlist"}
ALLOWED_MODES = {"interactive", "plan", "ask"}
ALLOWED_CLEAR_POLICIES = {"state-only"}
SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class DefinitionError(ValueError):
  """Raised when a personality definition or `_defaults.yaml` is invalid."""


@dataclass
class Personality:
  name: str
  title: str
  cli: str
  model: str | None
  effort: str | None
  mode: str
  delegates_to: tuple[str, ...]
  shell_allowlist: tuple[str, ...]
  clear_policy: str
  body: str
  source_path: pathlib.Path
  raw_text: str

  @property
  def definition_sha256(self) -> str:
    return hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()


@dataclass
class Defaults:
  schema_version: int
  per_cli: dict[str, dict[str, Any]] = field(default_factory=dict)
  lock: dict[str, Any] = field(default_factory=dict)
  replay: dict[str, Any] = field(default_factory=dict)
  raw_text: str = ""

  @property
  def defaults_sha256(self) -> str:
    return hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()


# ---- minimal YAML parser ---------------------------------------------------


def _strip_comment(line: str) -> str:
  # Strip a `#` comment unless inside double quotes. We do not support
  # single-quoted strings or escaped quotes — neither is in our schema.
  out = []
  in_quotes = False
  for ch in line:
    if ch == '"':
      in_quotes = not in_quotes
    if ch == "#" and not in_quotes:
      break
    out.append(ch)
  return "".join(out).rstrip()


_EMPTY_LIST_SENTINEL = object()


def _scalar(token: str) -> Any:
  s = token.strip()
  if s == "" or s.lower() == "null" or s == "~":
    return None
  if s.lower() == "true":
    return True
  if s.lower() == "false":
    return False
  if s == "[]":
    return []
  if s == "{}":
    return {}
  if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
    return s[1:-1]
  try:
    return int(s)
  except ValueError:
    pass
  try:
    return float(s)
  except ValueError:
    pass
  return s


def _indent_of(line: str) -> int:
  i = 0
  while i < len(line) and line[i] == " ":
    i += 1
  return i


def parse_yaml_minimal(text: str) -> Any:
  """Parse a tiny YAML subset.

  Supports:
    - top-level mappings,
    - nested mappings (indent must be a multiple of 2 spaces),
    - lists of scalars (`- foo`) and lists of mappings (`- key: value`),
    - scalars: int, string, null/~ , true/false, double-quoted string.

  Tabs are rejected. Anchors, multi-line scalars, flow style, and
  document separators are not supported.
  """
  raw_lines = text.splitlines()
  lines: list[tuple[int, str, int]] = []  # (indent, payload, lineno)
  for lineno, raw in enumerate(raw_lines, 1):
    if "\t" in raw:
      raise DefinitionError(
        f"yaml line {lineno}: tabs not allowed; use 2-space indent"
      )
    line = _strip_comment(raw)
    if not line.strip():
      continue
    indent = _indent_of(line)
    if indent % 2 != 0:
      raise DefinitionError(
        f"yaml line {lineno}: indent must be a multiple of 2 spaces"
      )
    lines.append((indent, line[indent:], lineno))

  pos = [0]

  def parse_block(min_indent: int) -> Any:
    if pos[0] >= len(lines):
      return None
    indent0, first, _ = lines[pos[0]]
    if indent0 < min_indent:
      return None
    if first.startswith("- "):
      return parse_list(indent0)
    return parse_map(indent0)

  def parse_map(indent: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    while pos[0] < len(lines):
      cur_indent, payload, lineno = lines[pos[0]]
      if cur_indent < indent:
        break
      if cur_indent > indent:
        raise DefinitionError(
          f"yaml line {lineno}: unexpected extra indentation"
        )
      if payload.startswith("- "):
        raise DefinitionError(
          f"yaml line {lineno}: list item where mapping expected"
        )
      if ":" not in payload:
        raise DefinitionError(
          f"yaml line {lineno}: expected `key: value`"
        )
      key, _, rest = payload.partition(":")
      key = key.strip()
      rest = rest.strip()
      pos[0] += 1
      if rest == "":
        # Nested block (map or list) at deeper indent, or empty value.
        nxt_indent = (
          lines[pos[0]][0] if pos[0] < len(lines) else -1
        )
        if pos[0] < len(lines) and nxt_indent > indent:
          out[key] = parse_block(nxt_indent)
        else:
          out[key] = None
      else:
        out[key] = _scalar(rest)
    return out

  def parse_list(indent: int) -> list[Any]:
    out: list[Any] = []
    while pos[0] < len(lines):
      cur_indent, payload, lineno = lines[pos[0]]
      if cur_indent < indent:
        break
      if cur_indent > indent:
        raise DefinitionError(
          f"yaml line {lineno}: unexpected extra indentation"
        )
      if not payload.startswith("- "):
        break
      item = payload[2:].strip()
      pos[0] += 1
      if ":" in item and not (item.startswith('"') and item.endswith('"')):
        # List of mappings: synthesize a sub-mapping starting with this key.
        key, _, rest = item.partition(":")
        sub: dict[str, Any] = {}
        if rest.strip() == "":
          # The sub-mapping continues at indent+2.
          nxt_indent = (
            lines[pos[0]][0] if pos[0] < len(lines) else -1
          )
          if pos[0] < len(lines) and nxt_indent > indent + 2:
            sub[key.strip()] = parse_block(nxt_indent)
          else:
            sub[key.strip()] = None
        else:
          sub[key.strip()] = _scalar(rest)
        # Continue collecting fields at indent+2.
        while pos[0] < len(lines):
          ci, pl, ln = lines[pos[0]]
          if ci < indent + 2 or pl.startswith("- "):
            break
          if ":" not in pl:
            raise DefinitionError(
              f"yaml line {ln}: expected mapping key inside list item"
            )
          k, _, v = pl.partition(":")
          pos[0] += 1
          v = v.strip()
          if v == "":
            nxt_indent = (
              lines[pos[0]][0] if pos[0] < len(lines) else -1
            )
            if pos[0] < len(lines) and nxt_indent > ci:
              sub[k.strip()] = parse_block(nxt_indent)
            else:
              sub[k.strip()] = None
          else:
            sub[k.strip()] = _scalar(v)
        out.append(sub)
      else:
        out.append(_scalar(item))
    return out

  return parse_block(0) or {}


# ---- defaults --------------------------------------------------------------


def _validate_defaults(data: Any, source: pathlib.Path) -> Defaults:
  if not isinstance(data, dict):
    raise DefinitionError(f"{source}: top-level must be a mapping")
  unknown = set(data) - {"schema_version", "defaults", "lock", "replay"}
  if unknown:
    raise DefinitionError(
      f"{source}: unknown top-level keys {sorted(unknown)}"
    )
  if data.get("schema_version") != 1:
    raise DefinitionError(f"{source}: schema_version must be 1")
  per_cli = data.get("defaults") or {}
  if not isinstance(per_cli, dict):
    raise DefinitionError(f"{source}: `defaults` must be a mapping")
  for cli in SUPPORTED_CLIS:
    if cli not in per_cli:
      raise DefinitionError(f"{source}: defaults.{cli} missing")
    block = per_cli[cli]
    if not isinstance(block, dict):
      raise DefinitionError(f"{source}: defaults.{cli} must be a mapping")
    if "command" not in block or not isinstance(block["command"], str):
      raise DefinitionError(f"{source}: defaults.{cli}.command must be string")
    if "model" not in block or not isinstance(block["model"], str):
      raise DefinitionError(f"{source}: defaults.{cli}.model must be string")
    if "effort" in block and block["effort"] is not None:
      if not isinstance(block["effort"], str):
        raise DefinitionError(
          f"{source}: defaults.{cli}.effort must be string or null"
        )
  lock = data.get("lock") or {}
  replay = data.get("replay") or {}
  if not isinstance(lock, dict):
    raise DefinitionError(f"{source}: `lock` must be a mapping")
  if not isinstance(replay, dict):
    raise DefinitionError(f"{source}: `replay` must be a mapping")
  return Defaults(
    schema_version=1,
    per_cli={cli: dict(per_cli[cli]) for cli in SUPPORTED_CLIS},
    lock=dict(lock),
    replay=dict(replay),
  )


def load_defaults(repo_root: pathlib.Path) -> Defaults:
  path = repo_root / DEFAULTS_REL
  if not path.exists():
    raise DefinitionError(f"missing {DEFAULTS_REL}")
  text = path.read_text(encoding="utf-8")
  data = parse_yaml_minimal(text)
  result = _validate_defaults(data, path)
  result.raw_text = text
  return result


# ---- personality.md --------------------------------------------------------


_FRONTMATTER_RE = re.compile(
  r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL
)


def _split_front_matter(text: str, source: pathlib.Path) -> tuple[str, str]:
  m = _FRONTMATTER_RE.match(text)
  if not m:
    raise DefinitionError(
      f"{source}: missing or malformed YAML front matter"
    )
  return m.group(1), m.group(2)


def _validate_personality(
  fm: dict[str, Any], body: str, source: pathlib.Path, expected_name: str,
  raw_text: str,
) -> Personality:
  unknown = set(fm) - ALLOWED_PERSONALITY_FIELDS
  unknown = {k for k in unknown if not k.startswith("x_")}
  if unknown:
    raise DefinitionError(
      f"{source}: unknown front-matter keys {sorted(unknown)}"
    )
  for required in ("name", "title", "cli"):
    if required not in fm:
      raise DefinitionError(f"{source}: front matter missing `{required}`")
  name = fm["name"]
  if not isinstance(name, str) or not SLUG_RE.match(name):
    raise DefinitionError(f"{source}: `name` must be a slug")
  if name != expected_name:
    raise DefinitionError(
      f"{source}: name {name!r} does not match parent dir {expected_name!r}"
    )
  if not isinstance(fm["title"], str) or not fm["title"]:
    raise DefinitionError(f"{source}: `title` must be a non-empty string")
  cli = fm["cli"]
  if cli not in SUPPORTED_CLIS:
    raise DefinitionError(
      f"{source}: `cli` must be one of {sorted(SUPPORTED_CLIS)}"
    )
  model = fm.get("model")
  if model is not None and not isinstance(model, str):
    raise DefinitionError(f"{source}: `model` must be string or null")
  effort = fm.get("effort")
  if effort is not None and not isinstance(effort, str):
    raise DefinitionError(f"{source}: `effort` must be string or null")
  mode = fm.get("mode", "interactive")
  if mode not in ALLOWED_MODES:
    raise DefinitionError(
      f"{source}: `mode` must be one of {sorted(ALLOWED_MODES)}"
    )
  delegates = fm.get("delegates_to") or []
  if not isinstance(delegates, list) or not all(
    isinstance(d, str) and SLUG_RE.match(d) for d in delegates
  ):
    raise DefinitionError(
      f"{source}: `delegates_to` must be a list of slugs"
    )
  tools = fm.get("tools") or {}
  if tools and not isinstance(tools, dict):
    raise DefinitionError(f"{source}: `tools` must be a mapping")
  bad_keys = set(tools) - ALLOWED_TOOLS_KEYS
  if bad_keys:
    raise DefinitionError(
      f"{source}: unknown tools keys {sorted(bad_keys)}"
    )
  shell_allow = tools.get("shell_allowlist") or []
  if not isinstance(shell_allow, list) or not all(
    isinstance(s, str) for s in shell_allow
  ):
    raise DefinitionError(
      f"{source}: `tools.shell_allowlist` must be a list of strings"
    )
  clear_policy = fm.get("clear_policy", "state-only")
  if clear_policy not in ALLOWED_CLEAR_POLICIES:
    raise DefinitionError(
      f"{source}: `clear_policy` must be `state-only`"
    )
  return Personality(
    name=name,
    title=fm["title"],
    cli=cli,
    model=model,
    effort=effort,
    mode=mode,
    delegates_to=tuple(delegates),
    shell_allowlist=tuple(shell_allow),
    clear_policy=clear_policy,
    body=body.strip("\n"),
    source_path=source,
    raw_text=raw_text,
  )


def load_personality(
  repo_root: pathlib.Path, name: str
) -> Personality:
  if not SLUG_RE.match(name or ""):
    raise DefinitionError(f"personality name {name!r} is not a valid slug")
  path = repo_root / PERSONALITIES_REL / name / "personality.md"
  if not path.exists():
    raise DefinitionError(
      f"personality {name!r} not found at {path.relative_to(repo_root)}"
    )
  text = path.read_text(encoding="utf-8")
  fm_text, body = _split_front_matter(text, path)
  fm = parse_yaml_minimal(fm_text)
  if not isinstance(fm, dict):
    raise DefinitionError(f"{path}: front matter must be a mapping")
  return _validate_personality(fm, body, path, name, text)


def list_personalities(repo_root: pathlib.Path) -> list[str]:
  base = repo_root / PERSONALITIES_REL
  if not base.is_dir():
    return []
  out = []
  for child in sorted(base.iterdir()):
    if not child.is_dir():
      continue
    if (child / "personality.md").exists():
      out.append(child.name)
  return out


# ---- effective config (defaults + per-personality override) ---------------


@dataclass
class EffectiveConfig:
  name: str
  cli: str
  command: str
  model: str
  effort: str | None
  mode: str
  delegates_to: tuple[str, ...]
  shell_allowlist: tuple[str, ...]
  body: str
  defaults: Defaults
  personality: Personality

  @property
  def definition_sha256(self) -> str:
    return self.personality.definition_sha256

  @property
  def defaults_sha256(self) -> str:
    return self.defaults.defaults_sha256


def resolve_effective(
  defaults: Defaults,
  personality: Personality,
  *,
  model_override: str | None = None,
  effort_override: str | None = None,
) -> EffectiveConfig:
  cli_block = defaults.per_cli[personality.cli]
  model = model_override or personality.model or cli_block["model"]
  if effort_override is not None:
    effort: str | None = effort_override
  elif personality.effort is not None:
    effort = personality.effort
  else:
    effort = cli_block.get("effort")
  return EffectiveConfig(
    name=personality.name,
    cli=personality.cli,
    command=cli_block["command"],
    model=model,
    effort=effort,
    mode=personality.mode,
    delegates_to=personality.delegates_to,
    shell_allowlist=personality.shell_allowlist,
    body=personality.body,
    defaults=defaults,
    personality=personality,
  )
