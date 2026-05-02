from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def check_requirements_block(text: str, source: pathlib.Path) -> list[str]:
  issues: list[str] = []
  in_req = False
  pending_pkg: str | None = None
  for line in text.splitlines():
    if "<<'REQ'" in line:
      in_req = True
      continue
    if in_req and line.strip() == "REQ":
      if pending_pkg:
        issues.append(f"{source}: requirement {pending_pkg} missing hash")
      in_req = False
      pending_pkg = None
      continue
    if not in_req:
      continue
    stripped = line.strip()
    if "--hash=sha256:" in stripped and pending_pkg:
      pending_pkg = None
      continue
    if not stripped or stripped.startswith("--") or stripped.startswith("#"):
      continue
    match = re.match(r"([A-Za-z0-9_.\-\[\]]+)==[^\s\\]+", stripped)
    if match:
      if pending_pkg:
        issues.append(f"{source}: requirement {pending_pkg} missing hash")
      pending_pkg = match.group(1)
  return issues


def main() -> int:
  issues: list[str] = []
  for spec in sorted((ROOT / "bootstrap/tools").glob("*.sh")):
    issues.extend(check_requirements_block(spec.read_text(encoding="utf-8"), spec))
  if issues:
    for issue in issues:
      print(f"dep-shape: {issue}", file=sys.stderr)
    return 1
  print("dep-shape: python requirement blocks are pinned with hashes")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
