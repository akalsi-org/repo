---
name: personality
description: Run or delegate to named repo personalities across Claude Code, Codex CLI, and GitHub Copilot CLI. Use when the user asks for CEO/CFO/CTO/infra-lead roles, persistent role sessions, cross-agent delegation, or clearing a personality session.
---

# personality

Named persistent role sessions backed by the repo `personality` verb
(`./repo.sh personality ...`). Definitions are committed under
`.agents/personalities/<name>/personality.md`. Per-machine session
state lives gitignored under `.local/personalities/<name>/`. Each
personality picks one backing CLI: `claude`, `codex`, or `copilot`.

The contract is `docs/research/multi_cli_personality_skill_spec.md`.
Re-read the spec before changing this skill.

## When this skill activates

- The user asks to talk to, ask, or "be" a named personality (CEO, CFO,
  CTO, infra-lead, security-lead, devil's-advocate, …).
- The user asks for a persistent role session, persistent CLI session,
  or `as-root <name>`.
- The user asks one personality to delegate to another via `personality
  ask`.
- The user asks to clear a personality's state without losing the
  definition.
- An edit touches `.agents/personalities/**`, `tools/personality`,
  `tools/personality_pkg/**`, or `tools/personality_tests/**`.

## Owned commands

The `personality` verb is the only operator surface.

| Subcommand | Purpose |
|------------|---------|
| `personality list` | Print roster + per-personality CLI/model/effort and last_active timestamp (or `never`). |
| `personality init <name> --cli <claude\|codex\|copilot>` | Scaffold `.agents/personalities/<name>/personality.md` from a template. |
| `personality as-root <name>` | Acquire the lock and exec the backing CLI in a foreground interactive session. Native resume when a `session_id` exists; fresh seed otherwise. |
| `personality ask <name> "<prompt>"` | One-shot non-interactive ask. stdout is just the reply. Updates `transcript.jsonl`. Native resume preferred; transcript replay fallback otherwise. |
| `personality clear <name>` | Wipe `.local/personalities/<name>/`. Definition under `.agents/personalities/<name>/` is left intact. |

Defaults live at `.agents/personalities/_defaults.yaml`:

- `claude` → `claude-sonnet-4-6`
- `codex` → `gpt-5.5`, reasoning effort `low`
- `copilot` → `gpt-5.4`

Per-personality `model` and `effort` in `personality.md` override the
defaults. `null` means "use the default."

## Cross-CLI spawn helper (delegation)

`personality ask <name> "<prompt>"` works as a Bash command from inside
any of the three CLIs, provided the CLI's tool/shell allowlist permits
it. The repo puts `tools/` on `PATH` via `repo.sh`, so the command is
spelled `./repo.sh personality ask <name> "<prompt>"` from outside, and
just `personality ask <name> "<prompt>"` from inside a `repo.sh`
session.

Per-CLI permission hints — paste these into the operator's allowlist:

- **Claude Code** — settings.local.json:
  `"allowedTools": ["Bash(./repo.sh personality ask *)"]`.
- **Codex CLI** — `$CODEX_HOME/rules/default.rules`:
  prefix `./repo.sh personality ask ` (or, conservatively, the absolute
  path to `tools/personality ask`). With `--ask-for-approval` policies
  the operator can also approve case-by-case.
- **GitHub Copilot CLI** — invocation flag:
  `--allow-tool 'shell(./repo.sh personality ask *)'`. Avoid
  `--allow-all-tools` and `COPILOT_ALLOW_ALL=1` for daily use.

The skill is authored once at `.agents/skills/personality/SKILL.md` and
reached through `.claude/skills`, `.codex/skills`, and
`.github/instructions/skills` symlinks.

## Native resume vs. transcript replay

Native resume is preferred for all three CLIs. The helper records the
native `session_id` in `.local/personalities/<name>/session_id`.

Transcript replay is the mandatory fallback when:

- `session_id` is missing.
- Native resume returns "not found", "invalid session", or equivalent.
- The caller passes `--replay` / `--no-native-resume`.
- `session_meta.yaml` says `replay_required: true`.

Replay reconstructs a synthesized prompt that begins with the current
role body, re-states earlier turns from `transcript.jsonl` (bounded by
`replay.max_turns` and `replay.max_bytes` in `_defaults.yaml`), and
appends the new caller prompt. Replay never mutates the user-level CLI
transcript stores; it only reads/writes `.local/personalities/<name>/`.

## What NOT to do

- Do not run a CLI's interactive `/clear` on behalf of a personality.
  Use `personality clear <name>` — it is the only v1 contract.
- Do not edit `.local/personalities/<name>/` by hand; the lock + state
  layout is owned by the helper.
- Do not bypass the lock. `as-root` is fail-fast on a held lock by
  design; queueing two interactive terminals is confusing.
- Do not hard-code GitHub login or org strings into a personality
  definition. Use `<login>`, `<org>`, `<vendor>`, etc. as placeholders.
- Do not invent new CLIs. The supported set is `claude`, `codex`,
  `copilot`. Adding a fourth requires an ADR amendment to the spec.
- Do not read `~/.claude`, `~/.codex`, `~/.copilot` directly. Treat
  them as the CLI's private store; only invoke through documented
  resume flags.
- Do not bake operator chat into a personality body. The body IS the
  personality's voice for the role; the operator-facing skill prose is
  caveman style, but the role bodies are normal English.
