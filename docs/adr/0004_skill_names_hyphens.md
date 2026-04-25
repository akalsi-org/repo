# Skill folder names use hyphens; everything else uses underscores

The template's general naming rule is underscore-only for files,
directories, config keys, Python modules, generated identifiers,
cache keys, and internal command names. Skill folder names under
`.agents/skills/` are an explicit carve-out: they use hyphens.

Reason: agent runtimes (Claude Code, Codex, Copilot) discover skills
by hyphenated folder name, and renaming would break upstream
discovery. CLI flags are already a similar carve-out for the same
reason — they follow external convention.

`agent_check` rejects `_` in skill folder names so the carve-out
stays clean.
