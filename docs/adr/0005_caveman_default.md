# Caveman mode is the default agent communication style

All agents operating in this template default to caveman mode (see
`.agents/skills/caveman/SKILL.md`): terse, no filler, technical
content exact. The default is hard-coded in `AGENTS.md` so agents
that do not consume Claude Code's auto-memory (Codex, Copilot)
honor it too.

Reason: token efficiency and signal density. Pleasantries and
articles waste budget without adding precision. Users can override
per-session ("stop caveman" / "normal mode") and the auto-clarity
exception still applies for security warnings, irreversible actions,
and multi-step sequences where fragment order risks misread.
