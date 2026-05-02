# Multi-CLI personality skill research

This note records the local findings for a future `personality` skill
that can run named roles through Claude Code, Codex CLI, and GitHub
Copilot CLI. The implementation is intentionally out of scope here.

## Local versions

The probes were run from the repository worktree on 2026-05-01.

| CLI | Probe | Observed result |
|-----|-------|-----------------|
| Claude Code | `claude --version` | `2.1.126 (Claude Code)` |
| Codex CLI | `codex --version` | `codex-cli 0.125.0`; the command also warned that it could not update `PATH` because the filesystem was read-only. |
| GitHub Copilot CLI | `copilot --version` | `GitHub Copilot CLI 1.0.36.` |
| GitHub Copilot through `gh` | `gh copilot --version` | `gh` is not installed in this environment. |

The usable Copilot install on this machine is the standalone `copilot`
binary, not the `gh copilot` extension path.

## 1. CLI session-resume mechanics

Claude Code has native resume. `claude --help` reports `-c,
--continue` to continue the most recent conversation in the current
directory, `-r, --resume [value]` to resume by session ID or open a
picker, and `--session-id <uuid>` to use a specific session ID. It also
has `--fork-session` for resuming into a new session ID. Local state is
stored outside the repo under `~/.claude/`; observed paths included
`~/.claude/history.jsonl`, `~/.claude/sessions/*.json`,
`~/.claude/session-env/<uuid>`, and `~/.claude/file-history/<uuid>/...`.
The official CLI reference documents the same resume forms:
`claude -c`, `claude -c -p "query"`, and `claude -r "<session-id>"
"query"` at https://docs.anthropic.com/en/docs/claude-code/cli-reference.

Codex CLI has native resume for both interactive and non-interactive
use. `codex --help` reports `codex resume` as "Resume a previous
interactive session (picker by default; use --last to continue the most
recent)". `codex resume --help` accepts `[SESSION_ID] [PROMPT]`,
`--last`, `--all`, and `--include-non-interactive`. `codex exec
resume --help` accepts `[SESSION_ID] [PROMPT]`, `--last`, `--all`,
`--json`, and `--output-last-message <FILE>`. Local state is under
`~/.codex/`; observed paths included `~/.codex/history.jsonl`,
`~/.codex/log/codex-tui.log`, `~/.codex/models_cache.json`, and
date-partitioned session files under `~/.codex/sessions/YYYY/MM/DD/`.

GitHub Copilot CLI has native resume in the standalone binary.
`copilot --help` reports `--continue`, `--resume[=value]`, and
`--name <name>`. Its examples cover `copilot --continue`,
`copilot --resume`, `copilot --resume=<session-id>`, resume by exact
name, resume by 7+ character ID prefix, and start/resume with a
specific UUID. `copilot help commands` also lists the interactive
`/resume`, `/new`, `/clear`, `/compact`, `/share`, `/search`, and
`/session` commands. Local state is under `~/.copilot/session-state/`;
observed session directories contain files such as `events.jsonl`,
`session.db`, `workspace.yaml`, `plan.md`, `checkpoints/`, `files/`,
and `inuse.<pid>.lock`. GitHub's current docs say Copilot CLI stores
session data locally and can resume previous sessions; see
https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/chronicle
and https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli.

All three CLIs therefore support native resume on this machine. The
personality helper should still keep its own `session_id` file because
each CLI stores session state in a different user-level tree and only
Codex exposes a clean non-interactive `exec resume` command shape.

## 2. Model and effort selection

Claude Code exposes model and effort directly. `claude --help` reports
`--model <model>` and `--effort <level>`, with effort choices `low`,
`medium`, `high`, `xhigh`, and `max`. The help text says a model may be
an alias such as `sonnet` or a full name such as `claude-sonnet-4-6`.
The default for this skill should invoke Claude as
`claude --model claude-sonnet-4-6`. No default Claude effort is required
by the issue; if a personality specifies one, pass `--effort <level>`.

Codex CLI exposes model as a flag and effort through config overrides.
`codex --help`, `codex resume --help`, and `codex exec --help` all
report `-m, --model <MODEL>`. They also report `-c, --config
<key=value>` for `~/.codex/config.toml` overrides. The config reference
uses `model_reasoning_effort` for the reasoning selector. The model
catalog from `codex debug models` included `gpt-5.5`, with supported
reasoning levels `low`, `medium`, `high`, and `xhigh`; its default was
`medium`. The skill default must override this as
`codex -m gpt-5.5 -c model_reasoning_effort='"low"' ...` for
interactive use and `codex exec -m gpt-5.5 -c
model_reasoning_effort='"low"' ...` for one-shot use. OpenAI's model
catalog also lists `gpt-5.5` and its reasoning options at
https://developers.openai.com/api/docs/models.

GitHub Copilot CLI exposes both model and effort directly. `copilot
--help` reports `--model <model>` and `--effort,
--reasoning-effort <level>`, with effort choices `low`, `medium`,
`high`, and `xhigh`. `copilot help config` lists `model` as a config
setting and includes `gpt-5.4` in the allowed model list. `copilot help
environment` reports `COPILOT_MODEL`, overridden by `--model` or
`/model`. The skill default must invoke Copilot as `copilot --model
gpt-5.4`. No default Copilot effort is required by the issue; if a
personality specifies one, pass `--reasoning-effort <level>`.

The uniform personality schema should use `model` and `effort`. The
implementation then maps `model` to `--model` for Claude and Copilot,
`-m` for Codex, and maps `effort` to `--effort` for Claude,
`-c model_reasoning_effort='"VALUE"'` for Codex, and
`--reasoning-effort` for Copilot.

## 3. System-prompt and role-context injection

Claude Code has the cleanest role injection path. `claude --help`
reports `--system-prompt <prompt>` and `--append-system-prompt
<prompt>`, plus file-free print mode with `-p`. It also has `--agent
<agent>` and `--agents <json>`, but the personality skill should not
depend on Claude-specific agents because the same definitions must run
through all three CLIs. The recommended path is to pass the personality
body through `--append-system-prompt` for both fresh interactive starts
and one-shot asks. On native resume, pass the same append prompt again
so the role is reasserted even if the resumed transcript has drifted.

Codex CLI has no explicit `--system-prompt` flag in local help. It does
support `-c model_instructions_file=...` through the config surface;
the Codex configuration reference names `model_instructions_file` as a
path to custom model instructions and warns that it overrides built-in
instructions. For this skill, that is too invasive because the helper
should preserve Codex's default agent behavior. The safer design is to
inject a deterministic first user message on new sessions and on replay
fallback: "Role context follows; obey it as session-level instruction."
For native resume, `as-root` can start from a session seeded with that
message, and `ask` can send a combined prompt containing a short role
refresh plus the caller prompt. This keeps implementation portable
without replacing Codex internals.

GitHub Copilot CLI has no explicit `--system-prompt` flag in local
help. It supports repository instructions via `AGENTS.md`, custom
instructions, skills, `--agent <agent>`, and `--no-custom-instructions`.
GitHub docs describe `AGENTS.md`, `.github/copilot-instructions.md`,
`.github/instructions/**/*.instructions.md`, and
`COPILOT_CUSTOM_INSTRUCTIONS_DIRS`; see
https://docs.github.com/en/copilot/how-tos/copilot-cli/add-custom-instructions.
For this skill, use the same portable injection strategy as Codex:
seed new sessions and replay fallback with the personality body as the
first role-context message, and include a compact role refresh on
native-resume one-shot asks.

## 4. State-dir contract

Committed definitions belong under `.agents/personalities/`. Each
personality is a directory named by a stable slug, with
`.agents/personalities/<name>/personality.md` as the canonical
definition. Defaults live in `.agents/personalities/_defaults.yaml`.
These files are source-controlled and are reviewed like skills.

Per-machine state belongs under `.local/personalities/<name>/`. The
repo already ignores `.local/`, so the session IDs, locks, transcripts,
and CLI adapter scratch files remain untracked. The minimum state set
is `session_id`, `session_meta.yaml`, `transcript.jsonl`, `lock`, and
`last_invocation.json`. The implementation may add
`replay_prompt.md`, `last_stdout.txt`, and `last_stderr.txt` as
debugging artifacts, but those are still state files, not definitions.

The helper should never inspect or mutate the user-level CLI storage
trees except by invoking each CLI's public resume flags. The local
state directory is the repo-owned contract; `~/.claude`, `~/.codex`,
and `~/.copilot` are external implementation details.

## 5. Cross-CLI spawn mechanism

All three CLIs can run shell commands. The portable spawn surface is a
repo command:

```bash
./repo.sh personality ask <name> "<prompt>"
```

The command must be usable from inside Claude, Codex, or Copilot when
their shell/tool permissions allow it. Claude has `--allowedTools` and
`--disallowedTools` for Bash tool policy. Codex has sandbox and approval
flags such as `--sandbox`, `--ask-for-approval`, and `--full-auto`.
Copilot has `--allow-tool`, `--deny-tool`, `--allow-all-tools`, and the
`COPILOT_ALLOW_ALL` environment variable. The skill body should tell
agents to allow exactly `./repo.sh personality ask *` when possible,
not broad shell access.

`personality ask` is non-interactive. It resolves the target
definition, acquires the target lock, selects native resume or replay
fallback, appends the caller prompt to `transcript.jsonl`, invokes the
target CLI, appends the reply, prints only the reply on stdout, and
returns a non-zero exit code with a clear stderr message on failure.
The caller should not need to know which CLI backs the target role.

## 6. Concurrency and locking

One process owns a personality at a time. The lock belongs to
`.local/personalities/<name>/lock`, not to the user-level CLI state
tree. It should be acquired before reading `session_id` or
`transcript.jsonl` and released after state has been durably updated.

Interactive `as-root` defaults to fail-fast if the lock is held,
because queueing an interactive terminal is confusing. One-shot `ask`
defaults to queueing with a finite timeout, because cross-personality
delegation is expected to happen while the caller waits for stdout.
Both modes need explicit flags to override the default:
`--lock-mode=fail|wait`, `--lock-timeout <duration>`, and `--stale-after
<duration>`.

Copilot's own local state uses `inuse.<pid>.lock` files inside session
directories. Those locks are useful evidence but are not the repo
contract. The personality helper should own an outer lock and let the
CLI own any inner lock it needs.

## 7. Skill symmetry across agents

The repository already exposes skills to all three surfaces. The
observed symlinks are `.claude/skills -> ../.agents/skills`,
`.codex/skills -> ../.agents/skills`, and `.github/instructions/skills
-> ../../.agents/skills`. Claude's skill docs say project skills live
under `.claude/skills/`. GitHub's docs say Copilot CLI supports project
skills from `.github/skills`, `.claude/skills`, or `.agents/skills`;
see https://docs.github.com/en/copilot/concepts/agents/about-agent-skills.
Codex uses the shared Agent Skills layout in this repo through the
`.codex/skills` symlink.

The new skill should therefore live once at
`.agents/skills/personality/SKILL.md` and rely on existing symlinks for
Claude, Codex, and Copilot discovery. The body must describe the same
`./repo.sh personality ...` command surface for all agents, with
per-CLI permission notes only where invocation differs.

## 8. `/clear` semantics

Claude's `/clear` is documented as clearing conversation history in an
interactive session. Copilot's `copilot help commands` reports `/clear`
as "Abandon this session and start fresh". Codex also has an
interactive session model and native resume, but local help does not
print a slash-command table.

The personality skill must not depend on any CLI's interactive
`/clear` command. Its clear operation is repo-owned:

```bash
./repo.sh personality clear <name>
```

That command deletes `.local/personalities/<name>/` after acquiring the
personality lock, then exits. It leaves
`.agents/personalities/<name>/personality.md` and
`.agents/personalities/_defaults.yaml` intact. The next `as-root` or
`ask` starts a fresh CLI session, writes a new `session_id`, and begins
a new `transcript.jsonl`.

## Gaps and design consequences

`gh copilot` is not available here. The implementation should support
the standalone `copilot` binary first and may later add a discovery
alias if `gh copilot` becomes present, but the locked spec should not
require `gh`.

Codex and Copilot do not expose a portable system-prompt flag equivalent
to Claude's `--append-system-prompt`. The spec therefore treats
role-context injection as helper-owned session seeding and refresh
messages for those CLIs.

Native resume exists for all three CLIs, but a transcript-replay
fallback is still required. It provides a uniform contract when a CLI's
resume store is missing, the recorded session ID no longer resolves, or
one-shot resume cannot be made reliable for a specific adapter.
