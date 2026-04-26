#!/usr/bin/env python3
"""Pack and publish bootstrap artifacts using only stdlib."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import pathlib
import tarfile
import sys
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.github.com"
ARTIFACT_FORMAT = "1"


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


def _sha256_text(text: str) -> str:
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_repo_config(root: pathlib.Path) -> dict[str, object]:
  path = root / ".agents" / "repo.json"
  if not path.is_file():
    return {}
  raw = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(raw, dict):
    raise SystemExit(".agents/repo.json must contain a JSON object")
  return raw


def _facet_config(root: pathlib.Path, name: str) -> dict[str, object]:
  raw = _load_repo_config(root).get("facet_config", {})
  if not isinstance(raw, dict):
    raise SystemExit("facet_config must be an object")
  value = raw.get(name, {})
  if not isinstance(value, dict):
    raise SystemExit(f"facet_config.{name} must be an object")
  return value


def _artifact_specs(root: pathlib.Path) -> list[dict[str, object]]:
  raw = _facet_config(root, "bootstrap").get("bootstrap_artifacts", [])
  if raw is None:
    return []
  if not isinstance(raw, list):
    raise SystemExit("facet_config.bootstrap.bootstrap_artifacts must be a list")
  specs: list[dict[str, object]] = []
  for item in raw:
    if not isinstance(item, dict):
      raise SystemExit("facet_config.bootstrap.bootstrap_artifacts entries must be objects")
    name = item.get("name")
    path = item.get("path")
    witnesses = item.get("witnesses", [])
    extra = item.get("extra", "")
    if not isinstance(name, str) or not isinstance(path, str):
      raise SystemExit("facet_config.bootstrap.bootstrap_artifacts entries need name and path")
    if not isinstance(witnesses, list) or not all(
        isinstance(v, str) for v in witnesses):
      raise SystemExit("facet_config.bootstrap.bootstrap_artifacts witnesses must be list[str]")
    if not isinstance(extra, str):
      raise SystemExit("facet_config.bootstrap.bootstrap_artifacts extra must be a string")
    specs.append({
        "name": name,
        "path": path,
        "witnesses": witnesses,
        "extra": extra,
    })
  return specs


def _input_sha(root: pathlib.Path, name: str, extra: str) -> str:
  key_path = root / "bootstrap" / "vars" / "local_cache_key.sh"
  key_text = key_path.read_text(encoding="utf-8") if key_path.is_file() else ""
  config_text = (root / ".agents" / "repo.json").read_text(encoding="utf-8")
  return _sha256_text(
      f"format={ARTIFACT_FORMAT}\n"
      f"name={name}\n"
      f"cache_key={hashlib.sha256(key_text.encode()).hexdigest()}\n"
      f"repo_config={hashlib.sha256(config_text.encode()).hexdigest()}\n"
      f"extra={extra}\n"
  )


def _pack_one(root: pathlib.Path, out_dir: pathlib.Path,
              spec: dict[str, object]) -> pathlib.Path | None:
  name = str(spec["name"])
  src = (root / str(spec["path"])).resolve()
  if not src.exists():
    print(f"bootstrap artifact skipped: {name} source missing: {src}",
          file=sys.stderr)
    return None
  for witness in spec["witnesses"]:
    if not (src / str(witness)).exists():
      raise SystemExit(f"cannot pack {name}: missing witness {witness}")
  digest = _input_sha(root, name, str(spec["extra"]))
  out_dir.mkdir(parents=True, exist_ok=True)
  archive = out_dir / f"repo-{name}-{digest}.tar.gz"
  manifest = json.dumps(
      {
          "format": ARTIFACT_FORMAT,
          "name": name,
          "input_sha": digest,
          "source": str(spec["path"]),
          "witnesses": spec["witnesses"],
      },
      sort_keys=True,
  ).encode("utf-8")
  with tarfile.open(archive, "w:gz") as tf:
    info = tarfile.TarInfo("manifest.json")
    info.size = len(manifest)
    tf.addfile(info, io.BytesIO(manifest))
    tf.add(src, arcname="payload")
  print(archive)
  return archive


def pack_configured_artifacts(root: pathlib.Path, out_dir: pathlib.Path) -> int:
  count = 0
  for spec in _artifact_specs(root):
    if _pack_one(root, out_dir, spec) is not None:
      count += 1
  if count == 0:
    print("bootstrap artifacts: none configured", file=sys.stderr)
  return 0


def main(argv: list[str] | None = None) -> int:
  p = argparse.ArgumentParser()
  sub = p.add_subparsers(dest="cmd")

  pack = sub.add_parser("pack")
  pack.add_argument("--root", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("REPO_ROOT", ".")))
  pack.add_argument("--out-dir", required=True, type=pathlib.Path)

  publish = sub.add_parser("publish")
  publish.add_argument("--repo", required=True, help="owner/name")
  publish.add_argument("--tag", required=True)
  publish.add_argument("artifacts", nargs="+", type=pathlib.Path)

  args = p.parse_args(argv)
  if args.cmd == "pack":
    return pack_configured_artifacts(args.root.resolve(), args.out_dir)
  if args.cmd is None:
    # Backward-compatible publish mode for callers that predate subcommands.
    legacy = argparse.ArgumentParser()
    legacy.add_argument("--repo", required=True, help="owner/name")
    legacy.add_argument("--tag", required=True)
    legacy.add_argument("artifacts", nargs="+", type=pathlib.Path)
    args = legacy.parse_args(argv)

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
