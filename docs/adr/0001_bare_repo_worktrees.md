# Bare repo + worktrees as the canonical layout

The template assumes a bare repo with sibling worktrees
(`<product>/.bare/` + `<product>/main/` + optional feature
worktrees) rather than a single regular clone. Worktrees give an
agent its own working tree per branch without re-cloning, share
`.local/` toolchain state, and let a human run multiple branches
side-by-side.

Single regular clones still work — every rule in `git-style/SKILL.md`
applies — but the AI-friendly default is bare + worktrees.
