#!/usr/bin/env python3
"""Publish bootstrap artifacts to a GitHub Release using only stdlib."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.github.com"


def resolve_token() -> str | None:
  """Find a GitHub token from env, falling back to ``~/github.token``.

  Order: ``GITHUB_TOKEN`` env, ``GH_TOKEN`` env, then a single-line
  ``~/github.token`` file (whitespace stripped). Returns ``None`` if no
  source is configured.
  """
  for var in ("GITHUB_TOKEN", "GH_TOKEN"):
    val = os.environ.get(var)
    if val:
      return val.strip()
  fallback = pathlib.Path.home() / "github.token"
  if fallback.is_file():
    text = fallback.read_text().strip()
    if text:
      return text
  return None


def _request(method: str, url: str, token: str, *, data: bytes | None = None,
             content_type: str = "application/json") -> tuple[int, bytes]:
  headers = {
      "Accept": "application/vnd.github+json",
      "Authorization": f"Bearer {token}",
      "X-GitHub-Api-Version": "2022-11-28",
  }
  if data is not None:
    headers["Content-Type"] = content_type
  req = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(req, timeout=60) as resp:
      return resp.status, resp.read()
  except urllib.error.HTTPError as e:
    return e.code, e.read()


def _json_request(method: str, url: str, token: str,
                  payload: dict[str, object] | None = None) -> tuple[int, object]:
  data = json.dumps(payload).encode() if payload is not None else None
  status, body = _request(method, url, token, data=data)
  if not body:
    return status, {}
  try:
    return status, json.loads(body)
  except json.JSONDecodeError:
    return status, {"message": body.decode("utf-8", "replace")}


def _release_by_tag(repo: str, tag: str, token: str) -> dict[str, object] | None:
  status, payload = _json_request("GET", f"{API}/repos/{repo}/releases/tags/{tag}", token)
  if status == 404:
    return None
  if status >= 300:
    raise RuntimeError(f"release lookup failed ({status}): {payload}")
  assert isinstance(payload, dict)
  return payload


def _create_release(repo: str, tag: str, token: str,
                    *, name: str, body: str) -> dict[str, object]:
  status, payload = _json_request(
      "POST",
      f"{API}/repos/{repo}/releases",
      token,
      {"tag_name": tag, "name": name, "body": body},
  )
  if status >= 300:
    raise RuntimeError(f"release create failed ({status}): {payload}")
  assert isinstance(payload, dict)
  return payload


_DEFAULT_RELEASE_NAME = "repo bootstrap artifacts v1"
_DEFAULT_RELEASE_BODY = (
    "Named, sha-keyed bootstrap acceleration artifacts. "
    "Source bootstrap remains canonical."
)


def ensure_release(repo: str, tag: str, token: str,
                   *, name: str = _DEFAULT_RELEASE_NAME,
                   body: str = _DEFAULT_RELEASE_BODY) -> dict[str, object]:
  """Find a release by tag, or create it. Public API used by sibling tools."""
  found = _release_by_tag(repo, tag, token)
  if found is not None:
    return found
  return _create_release(repo, tag, token, name=name, body=body)


def _release(repo: str, tag: str, token: str) -> dict[str, object]:
  return ensure_release(repo, tag, token)


def _asset_names(release: dict[str, object]) -> set[str]:
  assets = release.get("assets", [])
  if not isinstance(assets, list):
    return set()
  names = set()
  for asset in assets:
    if isinstance(asset, dict) and isinstance(asset.get("name"), str):
      names.add(asset["name"])
  return names


def _upload_url(release: dict[str, object], name: str) -> str:
  raw = release.get("upload_url")
  if not isinstance(raw, str):
    raise RuntimeError("release payload missing upload_url")
  base = raw.split("{", 1)[0]
  return f"{base}?{urllib.parse.urlencode({'name': name})}"


def upload_asset(release: dict[str, object], path: pathlib.Path, token: str,
                 *, asset_name: str | None = None,
                 noun: str = "bootstrap artifact") -> None:
  """Upload one file to an existing release. ``noun`` controls log wording."""
  name = asset_name or path.name
  content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
  url = _upload_url(release, name)
  status, body = _request(
      "POST",
      url,
      token,
      data=path.read_bytes(),
      content_type=content_type,
  )
  if status == 422:
    print(f"{noun} exists: {name}", file=sys.stderr)
    return
  if status >= 300:
    raise RuntimeError(f"upload {name} failed ({status}): {body.decode('utf-8', 'replace')}")
  print(f"uploaded {noun}: {name}", file=sys.stderr)


def asset_names(release: dict[str, object]) -> set[str]:
  """Return the set of asset names already attached to a release."""
  return _asset_names(release)


def _upload(release: dict[str, object], path: pathlib.Path, token: str) -> None:
  upload_asset(release, path, token)


def main(argv: list[str] | None = None) -> int:
  p = argparse.ArgumentParser()
  p.add_argument("--repo", required=True, help="owner/name")
  p.add_argument("--tag", required=True)
  p.add_argument("artifacts", nargs="+", type=pathlib.Path)
  args = p.parse_args(argv)

  token = resolve_token()
  if not token:
    raise SystemExit(
        "GITHUB_TOKEN or GH_TOKEN is required (or place a single-line "
        "PAT in ~/github.token)"
    )

  release = _release(args.repo, args.tag, token)
  existing = _asset_names(release)
  for path in args.artifacts:
    if not path.is_file():
      raise SystemExit(f"missing artifact: {path}")
    if path.name in existing:
      print(f"bootstrap artifact exists: {path.name}", file=sys.stderr)
      continue
    _upload(release, path, token)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
