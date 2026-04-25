from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path


def write(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


class TempRepo:
  def __init__(self) -> None:
    self._td = tempfile.TemporaryDirectory()
    self.root = Path(self._td.name)
    self._init_repo()

  def _init_repo(self) -> None:
    write(
      self.root / "AGENTS.md",
      """
      # AGENTS.md
      """,
    )
    write(
      self.root / "INTERACTIONS.md",
      """
      # INTERACTIONS.md
      """,
    )
    write(
      self.root / ".agents/skills/doc-sync/SKILL.md",
      """
      ---
      name: doc-sync
      description: keep docs current
      ---
      """,
    )
    write(
      self.root / ".agents/skills/build-commands/SKILL.md",
      """
      ---
      name: build-commands
      description: command routing
      ---
      """,
    )
    write(
      self.root / "src/example/AGENTS.md",
      """
      # example
      """,
    )
    write(
      self.root / "tools/sample-tool",
      """
      #!/bin/sh
      exit 0
      """,
    )
    (self.root / "tools/sample-tool").chmod(0o755)
    write(
      self.root / ".agents/kb-src/base.jsonl",
      """
      {"id":"build-fact","paths":["tools/sample-*"],"verbs":["change"],"skills":["build-commands"],"says":["Command changes use build-commands flow."],"refs":["AGENTS.md"],"checks":["./repo.sh lint"]}
      {"id":"src-fact","paths":["src/**"],"verbs":["change"],"says":["Read nested subsystem AGENTS."],"refs":["src/example/AGENTS.md"]}
      """,
    )
    write(
      self.root / ".agents/kb-src/tables/backlog.jsonl",
      """
      {"id":"bp1","area":"runtime-perf","priority":"P1","title":"Hot path heap alloc","path":"tools/sample-tool","paths":["tools/sample-*"],"suggested_fix":"stack buffer","detail":"heap alloc in hot path"}
      """,
    )
    write(
      self.root / ".agents/kb-src/tables/tool_catalog.jsonl",
      """
      {"id":"source-scan","name":"source scan","commands":["rg pattern src/"],"strengths":["fast discovery"]}
      {"id":"test","name":"test","commands":["./repo.sh test debug"],"strengths":["regression checks"]}
      {"id":"bench","name":"bench","commands":["./repo.sh bench debug"],"strengths":["hot path timing"]}
      {"id":"lint","name":"lint","commands":["./repo.sh lint"],"strengths":["cheap validation"]}
      """,
    )
    write(
      self.root / ".agents/kb-src/tables/tool_playbooks.jsonl",
      """
      {"id":"pb-runtime","areas":["runtime-perf"],"priorities":["P1"],"paths":["tools/sample-*"],"tool_ids":["bench","source-scan","test"],"why":"runtime perf wants search + tests"}
      """,
    )

  def cleanup(self) -> None:
    self._td.cleanup()
