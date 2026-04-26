# Bare repo + worktrees as the canonical layout

The template assumes a bare repo with sibling worktrees
(`<product>/.bare/` + `<product>/main/` + optional feature
worktrees) rather than a single regular clone. Worktrees give an
agent its own working tree per branch without re-cloning, share
`.local/` toolchain state, and let a human run multiple branches
side-by-side.

Single regular clones still work — every rule in `git-style/SKILL.md`
applies — but the AI-friendly default is bare + worktrees.

Backlog items that can run in parallel declare `parallel_mode`,
`worktree`, and `write_scope` in `.agents/ideas/ideas.jsonl`. Worktrees
isolate source edits while sharing `.local/`; agents must not run
parallel items with overlapping write scopes or any item marked
`serial`.
