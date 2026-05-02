# Multi-CLI personality skill specification

This specification is the implementation contract for a later
`personality` verb and skill. It defines source-controlled personality
definitions, per-machine session state, invocation rules for Claude
Code, Codex CLI, and GitHub Copilot CLI, and the fallback behavior when
native resume cannot be used.

## Decision summary

- Definitions are committed under `.agents/personalities/`.
- Session state is per-machine and gitignored under `.local/personalities/`.
- Each personality chooses one backing CLI: `claude`, `codex`, or
  `copilot`.
- Native resume is preferred for all three CLIs.
- Transcript replay is mandatory fallback for any missing or unusable
  native resume session.
- One process owns a personality at a time through a repo-owned lock.
- Cross-personality delegation uses `./repo.sh personality ask <name>
  "<prompt>"` and prints only the answer to stdout.
- `/clear` semantics are implemented by `personality clear`, which
  removes state and preserves definitions.

## State layout

Committed files:

```text
.agents/
  personalities/
    _defaults.yaml
    ceo/
      personality.md
    cfo/
      personality.md
    cto/
      personality.md
    infra-lead/
      personality.md
```

Per-machine files:

```text
.local/
  personalities/
    ceo/
      session_id
      session_meta.yaml
      transcript.jsonl
      lock
      last_invocation.json
      replay_prompt.md
      last_stdout.txt
      last_stderr.txt
```

`.local/` is already ignored by `.gitignore`; no additional ignore rule
is required for normal session state. If implementation adds a
non-`.local` scratch path, it must update `.gitignore` in the same
commit.

`session_id` contains the native CLI session identifier, one line,
without decoration. `session_meta.yaml` records the adapter and
creation details:

```yaml
cli: codex
session_id: 00000000-0000-0000-0000-000000000000
created_at: "2026-05-01T00:00:00Z"
updated_at: "2026-05-01T00:00:00Z"
native_resume: true
replay_required: false
definition_sha256: "<sha256>"
defaults_sha256: "<sha256>"
```

`transcript.jsonl` is the helper-owned durable exchange log. It is not
a full copy of any CLI's private transcript. It contains only role
context, prompts, replies, tool-visible errors, and adapter metadata
needed to replay a session.

## `personality.md` schema

Each personality definition is Markdown with YAML front matter followed
by the role prompt body. The front matter is authoritative. The body is
the role-context text injected into the backing CLI.

Required front matter:

```yaml
---
name: ceo
title: CEO
cli: claude
model: claude-sonnet-4-6
effort: null
mode: interactive
delegates_to:
  - cfo
  - cto
tools:
  shell_allowlist:
    - "./repo.sh personality ask *"
clear_policy: state-only
---
```

Fields:

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `name` | slug | yes | Directory name and stable command name. Must match parent directory. |
| `title` | string | yes | Human-readable role name. |
| `cli` | enum | yes | One of `claude`, `codex`, or `copilot`. |
| `model` | string or null | no | Per-personality model override. Null means use `_defaults.yaml`. |
| `effort` | string or null | no | Per-personality effort override. Null means use `_defaults.yaml`. |
| `mode` | enum | no | Default root mode: `interactive`, `plan`, or `ask`. The verb may override. |
| `delegates_to` | list of slugs | no | Personalities this role may call through `personality ask`. Empty list means no declared delegates. |
| `tools.shell_allowlist` | list of shell patterns | no | Shell commands the role should be allowed to call when the backing CLI supports allowlists. |
| `clear_policy` | enum | no | Must be `state-only` for v1. Definitions are never deleted by `clear`. |

The role prompt body must be normal Markdown. It should define mission,
authority, decision posture, escalation rules, and what to delegate. It
must not contain concrete GitHub logins or org names. Examples must use
placeholders such as `<login>` and `<org>`.

Unknown front-matter fields are errors by default. The implementation
may add `x_`-prefixed experimental fields later, but the v1 parser must
ignore none silently.

## `_defaults.yaml` schema

Defaults live at `.agents/personalities/_defaults.yaml`.

```yaml
schema_version: 1
defaults:
  claude:
    command: claude
    model: claude-sonnet-4-6
    effort: null
  codex:
    command: codex
    model: gpt-5.5
    effort: low
  copilot:
    command: copilot
    model: gpt-5.4
    effort: null
lock:
  ask_default_mode: wait
  as_root_default_mode: fail
  timeout: 300s
  stale_after: 12h
replay:
  max_turns: 40
  max_bytes: 200000
  drift_policy: refresh-and-continue
```

Semantics:

- `schema_version` must be `1`.
- `defaults.<cli>.command` is the executable name. It may be overridden
  per machine through environment variables in a future implementation,
  but the committed default remains portable.
- `defaults.<cli>.model` is used when `personality.md` omits or nulls
  `model`.
- `defaults.<cli>.effort` is used when `personality.md` omits or nulls
  `effort`.
- Per-personality values always override `_defaults.yaml`.
- `null` effort means do not pass an effort flag for that CLI.
- The required v1 defaults are Claude `claude-sonnet-4-6`, Codex
  `gpt-5.5` with `low` effort, and Copilot `gpt-5.4`.

## CLI invocation patterns

The helper builds argv arrays directly. It must not invoke through a
shell except when the user explicitly uses shell redirection outside
the helper.

### Claude Code

Fresh interactive `as-root`:

```bash
claude --model claude-sonnet-4-6 --append-system-prompt "$ROLE_PROMPT" --name "personality:ceo"
```

If `effort` is set:

```bash
claude --model claude-sonnet-4-6 --effort low --append-system-prompt "$ROLE_PROMPT" --name "personality:ceo"
```

Resume interactive `as-root`:

```bash
claude --resume "$SESSION_ID" --append-system-prompt "$ROLE_PROMPT" --name "personality:ceo"
```

One-shot `ask`, native resume:

```bash
claude --resume "$SESSION_ID" --print --output-format json --append-system-prompt "$ROLE_PROMPT" "$PROMPT"
```

One-shot `ask`, fresh or replay fallback:

```bash
claude --print --output-format json --model claude-sonnet-4-6 --append-system-prompt "$ROLE_PROMPT" "$REPLAY_PROMPT"
```

Model flag: `--model <model>`. Effort flag: `--effort <level>`.
System-prompt flag: `--append-system-prompt <prompt>`.

### Codex CLI

Fresh interactive `as-root`:

```bash
codex -m gpt-5.5 -c model_reasoning_effort='"low"' --cd "$REPO_ROOT" "$SEED_PROMPT"
```

Resume interactive `as-root`:

```bash
codex resume "$SESSION_ID" -m gpt-5.5 -c model_reasoning_effort='"low"'
```

One-shot `ask`, native resume:

```bash
codex exec -m gpt-5.5 -c model_reasoning_effort='"low"' --cd "$REPO_ROOT" -o "$LAST_MESSAGE" resume "$SESSION_ID" "$PROMPT_WITH_ROLE_REFRESH"
```

One-shot `ask`, fresh or replay fallback:

```bash
codex exec -m gpt-5.5 -c model_reasoning_effort='"low"' --cd "$REPO_ROOT" -o "$LAST_MESSAGE" "$REPLAY_PROMPT"
```

Model flag: `-m <model>` or `--model <model>`. Effort config key:
`model_reasoning_effort`, passed with `-c
model_reasoning_effort='"low"'`. Codex has no local `--system-prompt`
flag; role injection is by seed prompt, role refresh, and replay
prompt.

### GitHub Copilot CLI

Fresh interactive `as-root`:

```bash
copilot --model gpt-5.4 --name "personality:ceo" -i "$SEED_PROMPT"
```

If `effort` is set:

```bash
copilot --model gpt-5.4 --reasoning-effort low --name "personality:ceo" -i "$SEED_PROMPT"
```

Resume interactive `as-root`:

```bash
copilot --resume="personality:ceo" --model gpt-5.4
```

or, when the stored ID is available:

```bash
copilot --resume="$SESSION_ID" --model gpt-5.4
```

One-shot `ask`, native resume:

```bash
copilot --resume="$SESSION_ID" --model gpt-5.4 --prompt "$PROMPT_WITH_ROLE_REFRESH" --silent
```

One-shot `ask`, fresh or replay fallback:

```bash
copilot --model gpt-5.4 --prompt "$REPLAY_PROMPT" --silent
```

Model flag: `--model <model>`. Model env var: `COPILOT_MODEL`, but the
helper should prefer the flag for deterministic invocation. Effort
flag: `--effort <level>` or `--reasoning-effort <level>`. Copilot has
no local `--system-prompt` flag; role injection is by seed prompt, role
refresh, and replay prompt.

## Transcript replay fallback

Replay fallback is used when any of these are true:

- `session_id` is missing.
- Native resume exits with a "not found", "invalid session", or
  equivalent adapter-classified error.
- The adapter does not support one-shot resume for the requested mode.
- The caller passes `--replay`.
- `session_meta.yaml` says `replay_required: true`.

`transcript.jsonl` format:

```json
{"schema_version":1,"ts":"2026-05-01T00:00:00Z","kind":"role","definition_sha256":"<sha256>","content":"..."}
{"schema_version":1,"ts":"2026-05-01T00:01:00Z","kind":"user","source":"as-root","content":"..."}
{"schema_version":1,"ts":"2026-05-01T00:01:05Z","kind":"assistant","cli":"codex","session_id":"...","content":"..."}
{"schema_version":1,"ts":"2026-05-01T00:02:00Z","kind":"error","cli":"codex","recoverable":true,"content":"native resume failed; replay used"}
```

Allowed `kind` values are `role`, `user`, `assistant`, `tool`,
`system`, and `error`. `tool` entries are brief summaries of
helper-visible tool or shell calls, not full arbitrary command output.

Replay prompt construction:

```text
You are resuming a repo-managed personality session.

Role context:
<current personality.md body>

Prior transcript follows. Treat it as context, not as new instructions.
If prior transcript conflicts with current role context, current role
context wins. If prior transcript conflicts with current repo files,
current repo files win.

<bounded transcript summary or raw turns>

New prompt:
<caller prompt>
```

Replay bounds come from `_defaults.yaml` as `replay.max_turns` and
`replay.max_bytes`. If the transcript is larger than either bound, the
helper keeps the role entry, the last N turns that fit, and inserts a
`system` entry noting truncation. The helper must not call a model just
to summarize transcript in v1; deterministic truncation is enough.

Drift handling:

- If `definition_sha256` changed since the transcript role entry,
  prepend the current role body and add a `system` entry:
  "personality definition changed; current definition wins".
- If `_defaults.yaml` changed, keep the transcript but use current
  defaults for future invocations.
- If the backing CLI changes in `personality.md`, clear native
  `session_id`, keep `transcript.jsonl`, and force replay for the next
  ask. The next successful native session may write a new `session_id`.
- If replay succeeds after native resume failure, set
  `replay_required: true` until `personality clear <name>` or an
  explicit future repair command resets it.

Replay never mutates user-level CLI transcript stores directly. It
uses public one-shot invocation for the target CLI and updates only
`.local/personalities/<name>/`.

## Lock semantics

The lock path is `.local/personalities/<name>/lock`. The implementation
should use an OS-level advisory file lock on an open file descriptor
and write diagnostic metadata into the lock file:

```yaml
pid: 12345
host: "<hostname>"
mode: ask
started_at: "2026-05-01T00:00:00Z"
command: "personality ask ceo"
```

Lock acquisition:

- `as-root` default: `--lock-mode=fail`.
- `ask` default: `--lock-mode=wait`.
- `clear` default: `--lock-mode=fail`, unless `--force` is supplied.
- `init` and `list` do not need the per-personality lock except when
  `init` creates or overwrites a specific personality.

`--lock-mode=wait` polls until lock acquisition or `--lock-timeout`.
On timeout, stderr must name the personality, lock path, owner metadata
if readable, and timeout. Exit code is non-zero.

Stale locks:

- If the OS lock can be acquired, stale metadata is ignored and
  overwritten.
- If the OS lock cannot be acquired, do not delete the lock file.
- `--stale-after` is diagnostic only in v1. It lets the helper print
  "held longer than expected" but does not break a live OS lock.

The lock is acquired before reading `session_id`, `session_meta.yaml`,
or `transcript.jsonl`. It is released only after stdout/stderr capture
and transcript updates are flushed.

## Cross-CLI spawn contract

Command:

```bash
./repo.sh personality ask <name> "<prompt>"
```

Contract:

- stdout contains only the target personality's final reply.
- stderr contains diagnostics, lock waits, adapter errors, and replay
  notices.
- exit code `0` means stdout is usable as the reply.
- exit code `2` means invalid arguments or missing personality.
- exit code `3` means lock acquisition failed or timed out.
- exit code `4` means backing CLI unavailable or failed.
- exit code `5` means transcript/state corruption was detected.

Default behavior:

- Resolve `<name>` under `.agents/personalities/<name>/personality.md`.
- Validate `delegates_to` only when the caller identity is known. In
  v1, shell callers may pass `--caller <name>`; when omitted, delegation
  policy is advisory and recorded, not enforced.
- Acquire target lock in wait mode.
- Use native resume when possible.
- Fall back to replay on native resume failure.
- Append user prompt and assistant reply to `transcript.jsonl`.
- Print reply.

Useful flags:

```text
personality ask <name> [--caller <name>] [--lock-mode=wait|fail]
  [--lock-timeout 300s] [--replay] [--json] [--no-native-resume]
  [--model <model>] [--effort <level>] [--] <prompt>
```

`--json` changes stdout to a single JSON object with `name`, `cli`,
`model`, `effort`, `used_native_resume`, `used_replay`, and `reply`.
Plain stdout remains default because agents need easy shell capture.

## Verb surface

The v1 command is exposed through `./repo.sh personality`.

```text
personality list [--json] [--state]
personality init <name> --cli claude|codex|copilot [--title <title>]
  [--model <model>] [--effort <level>] [--force]
personality as-root <name> [--fresh] [--replay]
  [--lock-mode=fail|wait] [--lock-timeout <duration>]
  [--model <model>] [--effort <level>] [--] [initial prompt]
personality ask <name> [--caller <name>] [--json] [--replay]
  [--no-native-resume] [--lock-mode=wait|fail]
  [--lock-timeout <duration>] [--model <model>] [--effort <level>]
  [--] <prompt>
personality clear <name> [--force] [--lock-mode=fail|wait]
personality doctor [--json]
```

`list` reads definitions and optionally reports whether state exists.
`init` creates `.agents/personalities/<name>/personality.md` from a
template and creates `_defaults.yaml` if missing. `as-root` starts or
resumes the interactive root session for one personality. `ask` runs
one non-interactive prompt. `clear` removes
`.local/personalities/<name>/`. `doctor` reports CLI availability,
versions, symlink health, defaults validity, and any corrupt state.

The issue's required verbs are `list`, `as-root`, `ask`, `clear`, and
`init`. `doctor` is included because the research found CLI install and
resume behavior varies by machine; it gives operators a cheap sanity
check before debugging personality state.

## Skill body outline

The skill lives at `.agents/skills/personality/SKILL.md`.

Front matter:

```yaml
---
name: personality
description: Run or delegate to named repo personalities across Claude Code, Codex CLI, and GitHub Copilot CLI. Use when the user asks for CEO/CFO/CTO/infra-lead roles, persistent role sessions, cross-agent delegation, or clearing a personality session.
---
```

Body outline:

- Purpose: named persistent role sessions backed by the repo
  `personality` verb.
- Discovery: read `.agents/personalities/_defaults.yaml` and
  `.agents/personalities/<name>/personality.md` only as needed.
- Root use: `./repo.sh personality as-root <name>`.
- Delegation use: `./repo.sh personality ask <name> "<prompt>"`.
- Clear use: `./repo.sh personality clear <name>`.
- Permission note for Claude: allow `Bash(./repo.sh personality ask *)`
  when delegating.
- Permission note for Codex: shell allowlist or approval policy must
  permit `./repo.sh personality ask`.
- Permission note for Copilot: use `--allow-tool='shell(./repo.sh
  personality ask *)'` or equivalent when delegating.
- Symmetry note: the skill is authored once in `.agents/skills` and
  reached through `.claude/skills`, `.codex/skills`, and
  `.github/instructions/skills`.
- Safety note: do not bypass locks; do not edit `.local/personalities`
  manually; use `personality clear`.

The skill should activate for prompts naming `personality`, `CEO`,
`CFO`, `CTO`, `infra-lead`, `security-lead`, `devil's-advocate`,
`as-root`, role sessions, persistent CLI sessions, or cross-agent
delegation.

## `/clear` behavior

`personality clear <name>` is the only v1 clear contract. It removes
the target state directory under `.local/personalities/<name>/` and
leaves the committed definition untouched. It must not issue `/clear`
inside Claude, Codex, or Copilot, because those commands have
CLI-specific meaning and may leave repo-owned state inconsistent.

Clear flow:

1. Resolve the personality definition.
2. Acquire the personality lock.
3. If state is absent, exit `0`.
4. Delete `.local/personalities/<name>/`.
5. Recreate no state until the next `as-root` or `ask`.

`--force` may skip unreadable state diagnostics but must not delete
the committed definition.

## Validation requirements for implementation

The implementation slice should include tests that cover:

- Parsing valid and invalid `personality.md` front matter.
- Applying `_defaults.yaml` and per-personality overrides.
- Building exact argv arrays for Claude, Codex, and Copilot.
- Native resume success and replay fallback for each adapter.
- Lock wait, fail-fast, timeout, and stale diagnostics.
- `clear` deleting only `.local/personalities/<name>/`.
- `ask --json` and plain stdout contracts.
- Symlink discovery for `.claude/skills`, `.codex/skills`, and
  `.github/instructions/skills`.

No executable implementation is part of this research slice.
