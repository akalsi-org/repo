"""Render systemd unit templates with runtime-discovered values.

`render` keeps the original single-key ${LOGIN} contract used by
gh-keys-sync. `render_template` is the generic form: pass a mapping
of placeholder -> value and every `${KEY}` token gets substituted.
ADR-0014: no concrete login or per-host literal may live in any
tracked unit template, so substitution happens at install time.
"""
from __future__ import annotations

import pathlib
import re
from typing import Mapping


UNITS_DIR = pathlib.Path(__file__).resolve().parent / "units"

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def template_path(name: str) -> pathlib.Path:
  return UNITS_DIR / name


def render(template_name: str, login: str) -> str:
  if not login or not login.strip():
    raise ValueError("infra: cannot render unit with empty login")
  return render_template(template_name, {"LOGIN": login.strip()})


def render_template(template_name: str, values: Mapping[str, str]) -> str:
  """Substitute every ${KEY} placeholder via `values`.

  Raises ValueError on empty value, RuntimeError on any leftover
  placeholder after substitution. `%i` and other systemd specifiers
  pass through untouched because the regex only matches ${...}.
  """
  for k, v in values.items():
    if v is None or str(v).strip() == "":
      raise ValueError(f"infra: cannot render unit with empty value for {k}")
  src = template_path(template_name).read_text(encoding="utf-8")
  out = src
  for k, v in values.items():
    out = out.replace("${" + k + "}", str(v).strip())
  leftover = _PLACEHOLDER_RE.search(out)
  if leftover is not None:
    raise RuntimeError(
      f"infra: ${{{leftover.group(1)}}} unsubstituted after render"
    )
  return out
