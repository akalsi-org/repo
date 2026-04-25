---
name: git-style
description: Use when running git on behalf of the repo owner — commits, branches, remotes, worktrees. Produces commit messages, branch moves, and remote interactions that match this template's conventions, not a generic Conventional-Commits template.
---

# git-style

Operate git the way the template prescribes. Style is set by *observed*
recent commits, not by this document — reread `git log` if commits ahead
of you contradict what's written here.

## Read first

- `git log --pretty=fuller -12` on the active branch.
- `~/.gitconfig` for any `insteadOf` prefixes (e.g. `gh:` →
  `ssh://git@github.com/`). Don't rewrite remotes.

## Repo layout

This template assumes **bare repo + worktrees** for AI-friendly
parallelism:

```
<product>/
  .bare/              # bare git repo
  .local/             # shared toolchain cache, never per-worktree
  main/               # worktree for the main branch (canonical "repo root")
  <feature-branch>/   # additional worktrees as needed
```

- Run git **inside a worktree**, never inside `.bare/`.
- A worktree's `.git` file points back to `.bare/worktrees/<name>/`.
- Default branch is `main`. History stays **straight-line** — no merge
  commits from feature-branch merges; rebase or fast-forward.

If you discover the repo is a single regular clone (no `.bare/`),
treat it identically — every rule below still applies, the worktree
ones simply don't fire.

## Commit messages

**Subject** (≤ ~60 chars, no trailing period):

```
<scope>: <lowercase imperative summary>
```

- `<scope>` is a path-ish fragment, not a Conventional-Commits type.
  Examples:
  - Subsystem: `bootstrap:`, `tools:`, `agents:`, `docs:`, `ci:`.
  - Sub-path inside a subsystem: `tools/initialize:`, `bootstrap/tools:`.
  - Cross-cutting tags: `fix:`, `docs+ci:`, `tools+ci:`. Combine with
    `+` only when the change genuinely spans two areas.
- After the colon: **lowercase**, imperative (`drop`, `add`, `harden`,
  `sync`, `fix`), no period.
- Summarise the change, not the file list. If the scope already names
  the thing, don't repeat it.

**Body** (optional but preferred for non-trivial commits):

- Blank line after subject, then one or more paragraphs.
- Wrap around ~72 columns; don't break identifiers or numeric tables.
- Lead with the *why* or *what + motivation*, not a changelog.
- Use bullet lists for enumerations. Indent continuations two spaces.
- Reference `AGENTS.md §<n>` or `docs/adr/<NNNN>` when the commit
  implements or updates a documented contract. Don't reference
  issues / PRs in commit bodies — keep that in PR descriptions.

**Footer** (when the commit includes AI-authored content):

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Use the trailer the harness already emits. Don't add `Signed-off-by`
or other trailers the repo doesn't already use.

**Avoid**:

- `feat:` / `fix:` / `chore:` Conventional-Commits style — the template
  doesn't use it (the bare `fix:` is fine).
- WIP / checkpoint / squash-me commits — each commit is a coherent unit.
- Trailing periods on the subject. Emoji. Issue references in bodies.

## When to split vs. keep commits together

- **Keep related changes in one commit.** If the user had parallel edits
  going when you were invoked, roll them into the same commit and
  mention them in the message rather than splitting.
- Split when changes are *topically* independent (drive-by doc typo
  alongside a feature — commit the doc fix separately).

## Branches and remotes

- Push using whatever prefixes the user has configured (`git remote -v`
  shows actual URLs). Don't rewrite remotes.
- **Never force-push to `main`**; warn if asked. For feature branches,
  force-push only with explicit user go-ahead and prefer
  `--force-with-lease`.
- Don't create merge commits from feature branches. Rebase onto `main`
  or fast-forward merge.
- Don't run `git reset --hard`, `git checkout --`, `git clean -f`, or
  `git branch -D` without explicit user instruction.

## Worktree hygiene

- `git worktree add <path> <branch>` from inside any existing worktree
  (or from `.bare/`) creates a new sibling dir at `<path>`.
- `git worktree remove <path>` when done; `git worktree prune` for
  stale metadata. Don't delete a worktree dir by hand without `remove`.
- `.local/` is shared across worktrees — do not copy or move it
  per worktree.

## Hooks and pre-commit

- On hook failure: fix the underlying issue and create a **new** commit.
  Do not `--amend` — the failing commit didn't happen, so amend would
  modify the *previous* commit.
- Never pass `--no-verify`, `--no-gpg-sign`, or
  `-c commit.gpgsign=false` unless the user asked.

## Closeout alongside a commit

- If the commit changes anything covered by the doc-sync checklist
  (`AGENTS.md`, `CONTEXT.md`, `docs/adr/`, `.agents/skills/index.md`,
  `.agents/kb_src/`), update those **in the same commit** and say so
  in the message.
- Run `./repo.sh agent_check --stale-only` and `git diff --check`
  before handing back.

## Authoring pull requests

- Title: same shape as a commit subject (`<scope>: <summary>`).
- Body: `## Summary` + `## Test plan`, matching the harness default.
- Target branch is `main` unless the user says otherwise.
- Default `GITHUB_TOKEN` for `gh` is read from `~/github.token`
  (see `AGENTS.md` Integrations).
