"""Render systemd unit templates with the runtime-discovered login.

The ${LOGIN} placeholder is the ONLY substitution. Tests assert the
rendered output contains the expected login and that no other token
remains. ADR-0014: no concrete login may live in any tracked file,
so the templates themselves must keep the placeholder.
"""
from __future__ import annotations

import pathlib


UNITS_DIR = pathlib.Path(__file__).resolve().parent / "units"


def template_path(name: str) -> pathlib.Path:
  return UNITS_DIR / name


def render(template_name: str, login: str) -> str:
  if not login or not login.strip():
    raise ValueError("infra: cannot render unit with empty login")
  src = template_path(template_name).read_text(encoding="utf-8")
  rendered = src.replace("${LOGIN}", login.strip())
  if "${LOGIN}" in rendered:
    raise RuntimeError("infra: ${LOGIN} unsubstituted after render")
  return rendered
