"""GitHub identity discovery (ADR-0014, runtime discovery only).

Resolves the GitHub `<login>` whose .keys feed will populate
authorized_keys on adopted hosts. Discovery is RUNTIME via
`GET /user`. The token path follows the existing convention:
`GITHUB_TOKEN` env wins, else `~/github.token` mode 0600.

NO TRACKED FILE in this repo may carry a concrete login as a literal.
Tests mock `urllib.request.urlopen`; production reads the live API.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any


GITHUB_API_USER_URL = "https://api.github.com/user"
GITHUB_KEYS_URL_TEMPLATE = "https://github.com/{login}.keys"


class GhDiscoveryError(RuntimeError):
  pass


def _read_token(home: pathlib.Path | None = None) -> str:
  env = os.environ.get("GITHUB_TOKEN", "").strip()
  if env:
    return env
  home = home or pathlib.Path.home()
  path = home / "github.token"
  if not path.is_file():
    raise GhDiscoveryError(
      "infra: no github token; set GITHUB_TOKEN or write ~/github.token mode 0600"
    )
  raw = path.read_text(encoding="utf-8").strip()
  if not raw:
    raise GhDiscoveryError(f"infra: {path} is empty")
  return raw


def _opener_request(token: str) -> urllib.request.Request:
  req = urllib.request.Request(GITHUB_API_USER_URL)
  req.add_header("Authorization", f"Bearer {token}")
  req.add_header("Accept", "application/vnd.github+json")
  req.add_header("User-Agent", "repo-infra-adopt/1")
  return req


def discover_login(
  *,
  override: str | None = None,
  home: pathlib.Path | None = None,
  opener: Any = urllib.request.urlopen,
) -> str:
  """Return the GitHub login to use for keys-sync.

  - `override` short-circuits the API call (operator passed
    `--ssh-keys-github=<other>`).
  - Otherwise calls `GET /user` with the discovered token.
  - `opener` is parameterised so tests can inject a mock.
  """
  if override:
    override = override.strip()
    if not override:
      raise GhDiscoveryError("infra: --ssh-keys-github value is empty")
    return override

  token = _read_token(home=home)
  req = _opener_request(token)
  try:
    with opener(req, timeout=15) as resp:
      body = resp.read()
  except urllib.error.HTTPError as exc:
    raise GhDiscoveryError(
      f"infra: GET /user failed: HTTP {exc.code}"
    ) from exc
  except urllib.error.URLError as exc:
    raise GhDiscoveryError(
      f"infra: GET /user failed: {exc.reason}"
    ) from exc
  try:
    payload = json.loads(body)
  except json.JSONDecodeError as exc:
    raise GhDiscoveryError(f"infra: GET /user returned non-JSON: {exc}") from exc
  login = payload.get("login") if isinstance(payload, dict) else None
  if not isinstance(login, str) or not login.strip():
    raise GhDiscoveryError("infra: GET /user response missing login")
  return login.strip()


def keys_url(login: str) -> str:
  if not login or not login.strip():
    raise GhDiscoveryError("infra: keys_url called with empty login")
  return GITHUB_KEYS_URL_TEMPLATE.format(login=login.strip())
